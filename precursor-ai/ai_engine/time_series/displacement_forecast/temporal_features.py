"""Causal intermittent-observation and long-window trend features (skill Step 3).

Why: the 6-step increment window is dominated by the noise of the current date d_t, which appears with
opposite signs in the last input increment and in the label. The model therefore learns noise reversal
and applies it to genuinely moving pixels too (results/findings.md, section 2). A trend fitted over many
past acquisitions, and the current point's deviation from it, let the model tell trend from noise.

All features at date t use only acquisitions at dates <= t (causal). Unobserved values stay NaN here;
`build_samples` turns NaN into 0 and the `*_ok` / count features say whether a value exists.
Nothing is imputed into labels.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def window_trend(cum: np.ndarray, valid: np.ndarray, times: pd.DatetimeIndex, days: float, min_n: int) -> dict:
    """OLS line through valid (date, cum) points in (t - days, t], per pixel and date.

    Returns per-date grids:
      vel     slope in mm/day
      resid   cum[t] - line(t) for a valid current point (NaN otherwise): deviation of "now" from trend
      n       number of valid points used
    """
    T = len(times)
    td = (times - times[0]).days.values.astype(np.float64)
    vel = np.full(cum.shape, np.nan, np.float32)
    resid = np.full(cum.shape, np.nan, np.float32)
    n_out = np.zeros(cum.shape, np.int16)
    y_all = np.where(valid, cum, np.nan).astype(np.float64)
    for t in range(T):
        sel = (td > td[t] - days) & (td <= td[t])
        y = y_all[sel]
        x = td[sel][:, None, None]
        ok = np.isfinite(y)
        n = ok.sum(0)
        xm = np.where(ok, x, 0).sum(0) / np.maximum(n, 1)
        ym = np.where(ok, y, 0).sum(0) / np.maximum(n, 1)
        dx = np.where(ok, x - xm, 0.0)
        sxx = (dx ** 2).sum(0)
        b = (dx * np.where(ok, y - ym, 0.0)).sum(0) / np.maximum(sxx, 1e-9)
        good = (n >= min_n) & (sxx > 0)
        vel[t] = np.where(good, b, np.nan)
        fit_t = ym + b * (td[t] - xm)
        resid[t] = np.where(good & np.isfinite(y_all[t]), y_all[t] - fit_t, np.nan)
        n_out[t] = n
    return {"vel": vel, "resid": resid, "n": n_out}


def time_since_valid(valid: np.ndarray, times: pd.DatetimeIndex) -> np.ndarray:
    """Days since the last valid acquisition at or before t (0 if valid at t; NaN if never)."""
    td = (times - times[0]).days.values.astype(np.float64)
    last = np.full(valid.shape[1:], np.nan)
    out = np.full(valid.shape, np.nan, np.float32)
    for t in range(len(times)):
        last = np.where(valid[t], td[t], last)
        out[t] = td[t] - last
    return out


def build_temporal_features(cum, valid, times, windows=(144.0, 288.0), min_n=(6, 10)) -> dict:
    """Per-date [T, H, W] grids to pass as `extra_dyn` to dataset.build_samples."""
    feats = {}
    for d, m in zip(windows, min_n):
        w = window_trend(cum, valid, times, d, m)
        feats[f"vel{int(d)}"] = w["vel"]
        feats[f"resid{int(d)}"] = w["resid"]
        feats[f"vfrac{int(d)}"] = (w["n"] / max(1.0, d / 12.0)).astype(np.float32)   # share of expected 12-day slots
    tsv = time_since_valid(valid, times)
    feats["days_since_valid"] = np.where(np.isfinite(tsv), np.minimum(tsv, 365.0), 365.0).astype(np.float32)
    return feats
