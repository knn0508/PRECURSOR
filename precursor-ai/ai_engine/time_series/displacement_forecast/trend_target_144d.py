"""Derived observational 144-day trend target (skill v2, Step 4). Kept separate from the 12-day objective.

For an issue date t, the label is the robust (Huber) slope of VALID observed cumulative levels inside the
future window (t, t + window]. Data at or before t never enter the label, and masked-but-finite values are
never used (the caller passes NaN for them). Windows with too few distinct observations or too short a
span are unscorable (NaN), and that coverage is reported. This is a *derived observational trend target*,
not independent ground truth.
"""
from __future__ import annotations

import numpy as np


def future_slope(y: np.ndarray, td: np.ndarray, t_idx: np.ndarray, p_idx: np.ndarray, window: float = 144.0,
                 min_n: int = 6, min_span: float = 96.0, c: float = 1.345, iters: int = 6):
    """Labels for samples (t_idx[i], p_idx[i]). Returns slope (mm/day), slope SE, n, span; NaN if unscorable."""
    N = len(t_idx)
    slope = np.full(N, np.nan); se = np.full(N, np.nan); n_out = np.zeros(N, np.int16); span_out = np.zeros(N)
    for t in np.unique(t_idx):
        sel = np.where(t_idx == t)[0]
        w = np.where((td > td[t]) & (td <= td[t] + window))[0]          # strictly after t
        if len(w) < 2:
            continue
        Y = y[np.ix_(w, p_idx[sel])]; X = np.broadcast_to(td[w][:, None], Y.shape)
        ok = np.isfinite(Y); n = ok.sum(0)
        wt = ok.astype(np.float64)
        for _ in range(iters):
            sw = np.maximum(wt.sum(0), 1e-9)
            xm = (wt * np.where(ok, X, 0)).sum(0) / sw; ym = (wt * np.where(ok, Y, 0)).sum(0) / sw
            dx = np.where(ok, X - xm, 0.0)
            sxx = np.maximum((wt * dx ** 2).sum(0), 1e-9)
            b = (wt * dx * np.where(ok, Y - ym, 0.0)).sum(0) / sxx
            a = ym - b * xm
            r = np.where(ok, Y - (a + b * X), np.nan)
            s = 1.4826 * np.nanmedian(np.abs(r), axis=0) + 1e-6
            wt = np.where(ok, np.minimum(1.0, (c * s) / np.maximum(np.abs(np.nan_to_num(r)), 1e-9)), 0.0)
        span = np.where(n > 0, np.nanmax(np.where(ok, X, np.nan), 0) - np.nanmin(np.where(ok, X, np.nan), 0), 0)
        good = (n >= min_n) & (span >= min_span)
        resid_var = np.nansum(np.where(ok, r, 0) ** 2, 0) / np.maximum(n - 2, 1)
        slope[sel] = np.where(good, b, np.nan)
        se[sel] = np.where(good, np.sqrt(resid_var / sxx), np.nan)
        n_out[sel] = n; span_out[sel] = span
    return {"slope": slope, "se": se, "n": n_out, "span": span_out}
