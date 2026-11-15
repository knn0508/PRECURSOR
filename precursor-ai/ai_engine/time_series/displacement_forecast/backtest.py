"""Forecast-vs-reality backtest of the author's SAVED model on the newest OPERA dates in the processed stack. Nothing is retrained.

For every issue date D (>= first_issue) the model sees ONLY data up to D (causal features, train-only scaler) and forecasts the LOS increment to
D+12 d. The actual increment is cum[D+12] - cum[D] where both dates are valid measurements; masked or missing pixels have no actual and are
never scored. Baselines on the same pixels: zero-motion, and a ridge regression fitted on the training period (targets < 2023-01-01) only.

Held-out status (state it everywhere): the weights and scaler were fitted on data before 2023-01-01 (validation 2023). The 2024+ period was
inspected repeatedly by the source author, so these numbers are exploratory, not a fresh blind test. The processed stack's common-mode and
elevation-troposphere steps are per-date regressions on stable pixels chosen from the training period; the troposphere step is a high-pass, whose
exact look-ahead behaviour was not audited here.

    python -m displacement_forecast.backtest            # writes data/displacement_forecast/backtest/{backtest.json,grids.npz}
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import Ridge

from . import models as M
from . import train as TT
from .dataset import build_samples, chronological_split, target_index
from .saved_model import BUNDLE, LABEL, STATIC_NAMES, load_scaler

TRAIN_END, VAL_END = "2023-01-01", "2024-01-01"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(bundle: Path):
    import xarray as xr

    st = xr.open_dataset(bundle / "processed" / "opera_F16940_stack.nc")
    z = np.load(bundle / "processed" / "static_terrain.npz")
    static = np.stack([z[k] for k in STATIC_NAMES]).astype(np.float32)
    rain = pd.read_csv(bundle / "processed" / "imerg_daily_aoi.csv", index_col=0, parse_dates=True).iloc[:, 0]
    return st, pd.DatetimeIndex(st.time.values), static, rain


def forecast_at(cum, valid, coh, times, static, rain, k, sc, fidx, net, device, horizon=12.0):
    """Forecast grid [3,H,W] (q10,q50,q90; NaN = no estimate) and the sample set for issue index k, using ONLY indices <= k."""
    L = build_samples(cum[: k + 1], valid[: k + 1], coh[: k + 1], times[: k + 1], static, STATIC_NAMES, rain=rain, window=6, horizon=horizon,
                      min_valid_steps=4, pixel_stride=1, issue_indices=[k])
    q, _, _ = TT.predict(net, L, sc, fidx, device)
    g = np.full((3,) + cum.shape[1:], np.nan, np.float32)
    g[:, L.pix[:, 0], L.pix[:, 1]] = q.T
    return g, L


def _metrics(y, q50, q10, q90, ridge, last):
    e, z, r = np.abs(q50 - y), np.abs(y), np.abs(ridge - y)
    c = lambda a, b: float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 and np.std(a) > 0 and np.std(b) > 0 else None
    return {"n_pixels": int(len(y)), "MAE_model_mm": float(e.mean()), "MAE_zero_mm": float(z.mean()), "MAE_ridge_mm": float(r.mean()),
            "skill_vs_zero_pct": float((1 - e.mean() / z.mean()) * 100), "skill_vs_ridge_pct": float((1 - e.mean() / r.mean()) * 100),
            "cov80": float(np.mean((y >= q10) & (y <= q90))), "width80_mm": float(np.mean(q90 - q10)),
            "corr_forecast_vs_last_change": c(q50, last), "corr_forecast_vs_actual": c(q50, y), "corr_actual_vs_last_change": c(y, last)}


def _block_ci(rows, cols, a, b, n_boot=300, block=15, seed=0):
    """Spatial block bootstrap 95% CI of mean(a) - mean(b). Blocks of block x block pixels; optimistic if errors are correlated beyond a block."""
    rng = np.random.default_rng(seed)
    bid = (rows // block) * 1000 + (cols // block)
    ub, inv = np.unique(bid, return_inverse=True)
    sa, sb = np.bincount(inv, a), np.bincount(inv, b)
    cnt = np.bincount(inv).astype(float)
    out = []
    for _ in range(n_boot):
        s = rng.integers(0, len(ub), len(ub))
        out.append(sa[s].sum() / cnt[s].sum() - sb[s].sum() / cnt[s].sum())
    return [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]


def run(bundle: Path = BUNDLE, first_issue: str = "2025-12-29", device: str | None = None, horizon: float = 12.0, tol: float = 3.0) -> dict:
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    st, times, static, rain = _load(bundle)
    cum, valid, coh = st.cum_mm.values, st.valid.values, st.coherence.values
    sc, fidx, _ = load_scaler(bundle / "artifacts" / "scaler.npz")
    net = M.build("lstm_tcn", 6, len(fidx), 6, False, 64, 0.1).to(device)
    net.load_state_dict(torch.load(bundle / "artifacts" / "model.pt", map_location=device))
    net.eval()

    # ridge baseline: fitted on TRAIN-period samples only (targets < 2023-01-01), same recipe as the source (alpha=1, all features)
    ss = build_samples(cum, valid, coh, times, static, STATIC_NAMES, rain=rain, window=6, horizon=horizon, tol=tol, min_valid_steps=4, pixel_stride=2)
    tr = ss.subset(chronological_split(ss, TRAIN_END, VAL_END)["train"])
    Xtr, Str = sc.tx(tr)
    rm = Ridge(alpha=1.0).fit(np.concatenate([Xtr.reshape(len(tr), -1), Str], 1), sc.ty(tr.y))

    tgt = target_index(times, horizon, tol)
    issues = [k for k in range(len(times)) if times[k] >= pd.Timestamp(first_issue) and tgt[k] >= 0]
    H, W = cum.shape[1:]
    F, A, R = [], [], []
    per_date, pool = [], {k: [] for k in ("y", "q50", "q10", "q90", "ridge", "last", "r", "c")}
    for k in issues:
        m = tgt[k]
        g, L = forecast_at(cum, valid, coh, times, static, rain, k, sc, fidx, net, device, horizon)
        Xl, Sl = sc.tx(L)
        rd = sc.iy(rm.predict(np.concatenate([Xl.reshape(len(L), -1), Sl], 1)))
        act = np.where(valid[m] & valid[k], cum[m] - cum[k], np.nan).astype(np.float32)   # masked = not a measurement
        y = act[L.pix[:, 0], L.pix[:, 1]]
        ok = np.isfinite(y)
        q = g[:, L.pix[:, 0], L.pix[:, 1]]
        last = L.X[:, -1, 0]
        mt = _metrics(y[ok], q[1][ok], q[0][ok], q[2][ok], rd[ok], last[ok])
        per_date.append({"issue": str(times[k])[:10], "target": str(times[m])[:10], "horizon_days": float((times[m] - times[k]).days),
                         "pixels_with_forecast": int(len(L.pix)), "pixels_scored": int(ok.sum()), "actual_available_pct": float(np.isfinite(act).mean() * 100), **mt})
        F.append(g); A.append(act)
        for key, v in (("y", y[ok]), ("q50", q[1][ok]), ("q10", q[0][ok]), ("q90", q[2][ok]), ("ridge", rd[ok]), ("last", last[ok]), ("r", L.pix[ok, 0]), ("c", L.pix[ok, 1])):
            pool[key].append(v)
    P = {k: np.concatenate(v) for k, v in pool.items()}
    pooled = _metrics(P["y"], P["q50"], P["q10"], P["q90"], P["ridge"], P["last"])
    em, ez, er = np.abs(P["q50"] - P["y"]), np.abs(P["y"]), np.abs(P["ridge"] - P["y"])
    pooled["MAE_diff_model_minus_zero_ci95_mm"] = _block_ci(P["r"], P["c"], em, ez)
    pooled["MAE_diff_model_minus_ridge_ci95_mm"] = _block_ci(P["r"], P["c"], em, er)
    meta = {
        "label": LABEL, "kind": "BACKTEST, exploratory (see held_out_note)", "device": device, "model": "E3 lstm_tcn (author's saved weights, not retrained)",
        "frame": "F16940 ascending, Sentinel-1 C-band OPERA DISP-S1", "horizon_days": horizon,
        "issue_dates": [p["issue"] for p in per_date], "target_dates": [p["target"] for p in per_date],
        "test_period": f"issues {per_date[0]['issue']} to {per_date[-1]['issue']}, targets {per_date[0]['target']} to {per_date[-1]['target']}",
        "latest_data_date": str(times[-1])[:10],
        "held_out_note": "Weights/scaler fitted on data before 2023-01-01 (validation 2023). The 2024+ period was inspected repeatedly by the source author, so this is "
                         "exploratory, not a fresh blind test. Preprocessing (common-mode, elevation troposphere high-pass) was not audited for look-ahead.",
        "no_leakage": "Features for issue date D use only stack dates <= D (checked by a perturbation test); the scaler is train-only; the ridge baseline is train-only.",
        "scoring": "Only pixels with a valid measurement at both D and D+12; masked or missing pixels are never scored and never shown as zero.",
        "ci_note": "95% CI by spatial block bootstrap (15x15 px blocks, 300 resamples); optimistic if errors correlate beyond a block; 6 dates only.",
        "inputs_sha256": {"model.pt": _sha(bundle / "artifacts" / "model.pt"), "scaler.npz": _sha(bundle / "artifacts" / "scaler.npz"),
                          "opera_F16940_stack.nc": _sha(bundle / "processed" / "opera_F16940_stack.nc")},
        "pooled": pooled, "per_date": per_date, "height": int(H), "width": int(W),
    }
    return {"meta": meta, "forecast": np.stack(F), "actual": np.stack(A)}


def save(res: dict, bundle: Path = BUNDLE) -> Path:
    out = bundle / "backtest"
    out.mkdir(parents=True, exist_ok=True)
    (out / "backtest.json").write_text(json.dumps(res["meta"], indent=1), encoding="utf-8")
    np.savez_compressed(out / "grids.npz", forecast=res["forecast"].astype(np.float32), actual=res["actual"].astype(np.float32),
                        issue_dates=np.array(res["meta"]["issue_dates"]))
    return out


if __name__ == "__main__":
    r = run()
    print(json.dumps({k: v for k, v in r["meta"].items() if k in ("test_period", "pooled")}, indent=1))
    print("saved", save(r))
