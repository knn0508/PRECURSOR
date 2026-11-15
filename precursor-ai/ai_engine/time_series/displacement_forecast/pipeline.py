"""End-to-end run on arrays: build causal samples -> chronological split -> train LSTM-TCN -> held-out metrics vs baselines -> latest forecast.

Input is a stack (cum [T,H,W] mm, valid, coherence, times, static). The OPERA stack is fetched by `opera.py` only after the user approves
specific files; `synthetic_stack` exists for labelled smoke tests (a synthetic run is never a result: meta carries synthetic=True).

    python -m displacement_forecast.pipeline --synthetic --out <dir>      # CUDA if available
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from .dataset import Scaler, build_samples, chronological_split
from .train import baseline_predictions, fit_model, interval_metrics, predict, regression_metrics, ridge_baseline

LABEL = "RESEARCH / INFERRED / NOT A WARNING: LOS displacement-increment forecast, not a landslide probability."


def synthetic_stack(T: int = 70, H: int = 12, W: int = 12, seed: int = 0):
    """Labelled SYNTHETIC stack: one moving patch, white noise elsewhere. Pipeline mechanics only."""
    rng = np.random.default_rng(seed)
    times = pd.date_range("2018-01-01", periods=T, freq="12D")
    t = np.arange(T, dtype=np.float32) * 12
    rate = np.zeros((H, W), np.float32)
    rate[3:7, 3:7] = 0.15
    cum = rate[None] * t[:, None, None] + rng.normal(0, 1.0, (T, H, W)).astype(np.float32)
    return cum, np.ones_like(cum, bool), np.full_like(cum, 0.9), times, np.zeros((2, H, W), np.float32), ["elev", "slope"]


def pick_device(device: str | None = None) -> str:
    return device or ("cuda" if torch.cuda.is_available() else "cpu")


def run(cum, valid, coh, times, static, static_names, *, train_end, val_end, window=6, horizon=12.0, model="lstm_tcn",
        max_epochs=40, patience=5, seed=0, device=None, synthetic=False) -> dict:
    device = pick_device(device)
    ss = build_samples(cum, valid, coh, times, static, static_names, window=window, horizon=horizon, pixel_stride=1)
    sp = chronological_split(ss, train_end, val_end)
    if min(len(sp["train"]), len(sp["val"]), len(sp["test"])) == 0:
        raise ValueError(f"empty split: {({k: len(v) for k, v in sp.items()})}; adjust train_end/val_end")
    tr, va, te = (ss.subset(sp[k]) for k in ("train", "val", "test"))
    sc = Scaler().fit(tr)
    net, info = fit_model(model, tr, va, sc, seed=seed, max_epochs=max_epochs, patience=patience, device=device)
    q, _, _ = predict(net, te, sc, device=device)
    metrics = {"test": {"model": {**regression_metrics(te.y, q[:, 1]), **interval_metrics(te.y, q)},
                        **{k: regression_metrics(te.y, v) for k, v in baseline_predictions(te).items()},
                        "ridge_linear": regression_metrics(te.y, ridge_baseline(tr, te, sc))}}
    last = build_samples(cum, valid, coh, times, static, static_names, window=window, horizon=horizon, pixel_stride=1,
                         issue_indices=[len(times) - 1])
    ql, _, _ = predict(net, last, sc, device=device)
    H, W = cum.shape[1:]
    grid = np.full((3, H, W), np.nan, np.float32)  # NaN = no reliable estimate (never zero)
    grid[:, last.pix[:, 0], last.pix[:, 1]] = ql.T
    meta = {"label": LABEL, "synthetic": bool(synthetic), "device": device, "model": model, "seed": seed, "horizon_days": horizon,
            "issue_time": str(times[-1]), "splits": {k: int(len(v)) for k, v in sp.items()}, "n_params": info["n_params"],
            "epochs": info["epochs"], "train_seconds": round(info["train_seconds"], 2)}
    return {"meta": meta, "metrics": metrics, "forecast": grid, "state_dict": net.state_dict()}


def save(res: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps(res["meta"], indent=1), encoding="utf-8")
    if not res["meta"]["synthetic"]:  # a synthetic run writes no metrics a report could cite
        (out / "metrics.json").write_text(json.dumps(res["metrics"], indent=1), encoding="utf-8")
    np.save(out / "forecast_q10_q50_q90.npy", res["forecast"])
    torch.save(res["state_dict"], out / "model.pt")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true", help="labelled synthetic smoke run")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--device", default=None)
    a = ap.parse_args()
    if not a.synthetic:
        raise SystemExit("real stacks need user-approved OPERA files (see README); only --synthetic is runnable without them")
    s = synthetic_stack()
    r = run(*s, train_end="2019-06-01", val_end="2020-03-01", max_epochs=5, device=a.device, synthetic=True)
    save(r, a.out)
    print(json.dumps(r["meta"], indent=1))
