"""Shared, frozen data setup for the v2 trend-first experiments (same as notebook B0 / step3_ablation).

One build_samples call (base features + rain + static, pixel_stride 2, horizon 12 +- 3 d) on the processed
stack (common-mode + elevation tropo). Split: train < 2023, val 2023, test >= 2024. Regimes:
  moving   pixel whose TRAIN-period median |12-d speed| > train p90 (known at forecast time)
  strong   |observed label| > train p95 (label-defined, evaluation only)
  noise_sd SD of 12-day increments on TRAIN-period stable pixels (training data only)
Per-pixel series for the trend models are taken at the sampled pixels only (P = ~7 000).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from .ancillary import dem_on_grid
from .dataset import build_samples, chronological_split, Scaler
from .discovery import AOI

ROOT = Path(__file__).resolve().parents[2]
TRAIN_END, VAL_END = "2023-01-01", "2024-01-01"
AOI_PB = AOI("portuguese_bend_rpv", -118.380, 33.725, -118.320, 33.765)
STATIC_NAMES = ["elevation", "slope_deg", "aspect_sin", "aspect_cos", "curvature"]
BASE = ["inc_mm", "dt_days", "vel_mm_day", "coherence", "valid"]


def load(with_rain=True):
    st = xr.open_dataset(ROOT / "data/processed/opera_F16940_stack.nc")
    times = pd.DatetimeIndex(st.time.values)
    cum, valid, coh = st.cum_mm.values, st.valid.values, st.coherence.values
    terr = dem_on_grid(st.x.values, st.y.values, st.attrs["crs_wkt"], AOI_PB)
    static = np.stack([np.nan_to_num(terr[k]) for k in STATIC_NAMES]).astype(np.float32)
    rain = pd.read_csv(ROOT / "data/processed/imerg_daily_aoi.csv", index_col=0, parse_dates=True).iloc[:, 0] if with_rain else None
    ss = build_samples(cum, valid, coh, times, static, STATIC_NAMES, rain=rain, window=6, horizon=12.0, tol=3.0,
                       min_valid_steps=4, pixel_stride=2)
    sp = chronological_split(ss, TRAIN_END, VAL_END)
    TR, VA, TE = (ss.subset(sp[k]) for k in ("train", "val", "test"))
    td = (times - times[0]).days.values.astype(np.float64)
    # per-pixel observed series at the sampled pixels (NaN where not a valid observation)
    H, W = cum.shape[1:]
    rows, cols = np.mgrid[0:H:2, 0:W:2]
    rows, cols = rows.ravel(), cols.ravel()
    col_of = {(r, c): i for i, (r, c) in enumerate(zip(rows, cols))}
    y = np.where(valid, cum, np.nan)[:, rows, cols].astype(np.float64)
    t_of = {t: i for i, t in enumerate(times.values)}

    def index(S):
        k = np.array([t_of[t] for t in S.issue_time]); p = np.array([col_of[(r, c)] for r, c in S.pix])
        return k, p

    rate = pd.DataFrame({"r": TR.pix[:, 0], "c": TR.pix[:, 1], "v": np.abs(TR.y / TR.h_days)}).groupby(["r", "c"]).v.median()
    mthr, hthr = float(np.quantile(rate, 0.90)), float(np.quantile(np.abs(TR.y), 0.95))
    moving_of = lambda S: rate.reindex(pd.MultiIndex.from_arrays([S.pix[:, 0], S.pix[:, 1]])).values > mthr
    tr_mv = moving_of(TR)
    noise_sd = float(np.std(TR.y[~tr_mv]))                       # train-only stable increment SD
    reg = pd.read_csv(ROOT / "results/qa_audit_pixels.csv").region.to_numpy(dtype=str).reshape(H, W)
    return dict(st=st, times=times, td=td, cum=cum, valid=valid, ss=ss, sp=sp, TR=TR, VA=VA, TE=TE, sc=Scaler().fit(TR),
                y=y, rows=rows, cols=cols, index=index, moving_of=moving_of, mthr=mthr, hthr=hthr,
                noise_sd=noise_sd, region=reg)


def regimes(D, S):
    mv = D["moving_of"](S)
    core = D["region"][S.pix[:, 0], S.pix[:, 1]] == "core"
    return {"all": np.ones(len(S.y), bool), "stable": ~mv, "moving": mv, "strong": np.abs(S.y) > D["hthr"], "core": core}


def cluster_boot_ci(stat_fn, groups, n_boot=200, seed=0):
    """Percentile CI of stat_fn(index_array) resampling whole groups (pixels) with replacement."""
    rng = np.random.default_rng(seed)
    u, inv = np.unique(groups, return_inverse=True)
    members = [np.where(inv == g)[0] for g in range(len(u))]
    vals = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(u), len(u))
        idx = np.concatenate([members[g] for g in pick])
        vals.append(stat_fn(idx))
    return float(np.nanpercentile(vals, 2.5)), float(np.nanpercentile(vals, 97.5))


def metrics(D, S, p, prefix, q=None, k_signal=1.0):
    """Regime metrics for point forecasts p (and optional quantiles q) against observed labels S.y."""
    R = regimes(D, S); y = S.y; out = {f"{prefix}n": int(len(y))}
    for name, m in R.items():
        if not m.any():
            continue
        e = y[m] - p[m]
        out[f"{prefix}MAE_{name}"] = float(np.mean(np.abs(e)))
        out[f"{prefix}RMSE_{name}"] = float(np.sqrt(np.mean(e ** 2)))
        out[f"{prefix}bias_{name}"] = float(np.mean(p[m] - y[m]))
        out[f"{prefix}n_{name}"] = int(m.sum())
        if q is not None:
            out[f"{prefix}cov80_{name}"] = float(np.mean((y[m] >= q[m, 0]) & (y[m] <= q[m, 2])))
    thr = k_signal * D["noise_sd"]
    for name in ("moving", "strong"):
        m = R[name] & (np.abs(y) > thr)                        # high-signal labels only; near-zero signs are noise
        out[f"{prefix}dir_acc_{name}"] = float(np.mean(np.sign(p[m]) == np.sign(y[m]))) if m.any() else np.nan
        out[f"{prefix}n_dir_{name}"] = int(m.sum())
    d = pd.DataFrame({"r": S.pix[:, 0], "c": S.pix[:, 1], "y": y, "p": p})[R["moving"]]
    g = d.groupby(["r", "c"]).agg(y=("y", "sum"), p=("p", "sum"), n=("y", "size")); g = g[g.n >= 10]
    out[f"{prefix}pixel_cum_sign_moving"] = float(np.mean(np.sign(g.y) == np.sign(g.p)))
    out[f"{prefix}pixel_cum_corr_moving"] = float(np.corrcoef(g.y, g.p)[0, 1]) if g.p.std() > 0 else np.nan
    out[f"{prefix}pixel_cum_bias_moving_mm"] = float(np.mean(g.p - g.y))
    out[f"{prefix}n_moving_pixels"] = int(len(g))
    out[f"{prefix}n_unique_pixels"] = int(len(np.unique(S.pix, axis=0)))
    out[f"{prefix}n_dates"] = int(len(np.unique(S.issue_time)))
    return out
