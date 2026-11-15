"""Causal robust velocity estimators on observed cumulative LOS levels (skill v2, T1/T2).

Inputs are per-pixel series y[T, P] (mm, NaN where not a valid observation) and acquisition days td[T].
At date t only dates in (td[t] - window, td[t]] are used, so estimates are strictly past-only (<= t).
Each estimator returns per-date arrays:
  vel    slope (mm/day)
  level  fitted level at td[t]
  resid  y[t] - level (deviation of the current observation from the fitted trend; NaN if y[t] missing)
  n      number of valid observations used
  span   days between the first and last valid observation used
Estimates with n < min_n or span < min_span are NaN, meaning "abstain". The caller decides the fallback.
"""
from __future__ import annotations

import numpy as np


def _window(td, t, days):
    return np.where((td > td[t] - days) & (td <= td[t]))[0]


def _finish(Y, X, b, a, td_t, y_t, n, span, min_n, min_span):
    ok = (n >= min_n) & (span >= min_span)
    level = a + b * td_t
    return (np.where(ok, b, np.nan), np.where(ok, level, np.nan),
            np.where(ok & np.isfinite(y_t), y_t - level, np.nan))


def ols(y, td, days, min_n=6, min_span=60.0):
    T, P = y.shape
    out = {k: np.full((T, P), np.nan, np.float32) for k in ("vel", "level", "resid")}
    out["n"] = np.zeros((T, P), np.int16); out["span"] = np.zeros((T, P), np.float32)
    for t in range(T):
        w = _window(td, t, days)
        Y = y[w]; X = np.broadcast_to(td[w][:, None], Y.shape)
        ok = np.isfinite(Y); n = ok.sum(0)
        xm = np.where(ok, X, 0).sum(0) / np.maximum(n, 1); ym = np.where(ok, Y, 0).sum(0) / np.maximum(n, 1)
        dx = np.where(ok, X - xm, 0.0)
        b = (dx * np.where(ok, Y - ym, 0.0)).sum(0) / np.maximum((dx ** 2).sum(0), 1e-9)
        a = ym - b * xm
        span = np.where(n > 0, np.nanmax(np.where(ok, X, np.nan), 0) - np.nanmin(np.where(ok, X, np.nan), 0), 0)
        v, l, r = _finish(Y, X, b, a, td[t], y[t], n, span, min_n, min_span)
        out["vel"][t], out["level"][t], out["resid"][t], out["n"][t], out["span"][t] = v, l, r, n, span
    return out


def theil_sen(y, td, days, min_n=6, min_span=60.0):
    """Median of pairwise slopes; intercept = median(y - b x). Robust to isolated jumps (~29 % breakdown)."""
    T, P = y.shape
    out = {k: np.full((T, P), np.nan, np.float32) for k in ("vel", "level", "resid")}
    out["n"] = np.zeros((T, P), np.int16); out["span"] = np.zeros((T, P), np.float32)
    for t in range(T):
        w = _window(td, t, days)
        Y = y[w]; x = td[w]
        ok = np.isfinite(Y); n = ok.sum(0)
        if len(w) >= 2:
            i, j = np.triu_indices(len(w), 1)
            S = (Y[j] - Y[i]) / (x[j] - x[i])[:, None]
            b = np.nanmedian(S, axis=0)
        else:
            b = np.full(P, np.nan)
        a = np.nanmedian(Y - b[None] * x[:, None], axis=0)
        span = np.where(n > 0, np.nanmax(np.where(ok, x[:, None], np.nan), 0) - np.nanmin(np.where(ok, x[:, None], np.nan), 0), 0)
        v, l, r = _finish(Y, None, b, a, td[t], y[t], n, span, min_n, min_span)
        out["vel"][t], out["level"][t], out["resid"][t], out["n"][t], out["span"][t] = v, l, r, n, span
    return out


def huber(y, td, days, min_n=6, min_span=60.0, c=1.345, iters=6):
    """Huber M-estimate of the line by IRLS (scale = 1.4826 MAD of residuals)."""
    T, P = y.shape
    out = {k: np.full((T, P), np.nan, np.float32) for k in ("vel", "level", "resid")}
    out["n"] = np.zeros((T, P), np.int16); out["span"] = np.zeros((T, P), np.float32)
    for t in range(T):
        w = _window(td, t, days)
        Y = y[w]; X = np.broadcast_to(td[w][:, None], Y.shape)
        ok = np.isfinite(Y); n = ok.sum(0)
        wt = ok.astype(np.float64)
        for _ in range(iters):
            sw = np.maximum(wt.sum(0), 1e-9)
            xm = (wt * np.where(ok, X, 0)).sum(0) / sw; ym = (wt * np.where(ok, Y, 0)).sum(0) / sw
            dx = np.where(ok, X - xm, 0.0)
            b = (wt * dx * np.where(ok, Y - ym, 0.0)).sum(0) / np.maximum((wt * dx ** 2).sum(0), 1e-9)
            a = ym - b * xm
            r = np.where(ok, Y - (a + b * X), np.nan)
            s = 1.4826 * np.nanmedian(np.abs(r), axis=0) + 1e-6
            u = np.abs(np.nan_to_num(r)) / (c * s)
            wt = np.where(ok, np.minimum(1.0, 1.0 / np.maximum(u, 1e-9)), 0.0)
        span = np.where(n > 0, np.nanmax(np.where(ok, X, np.nan), 0) - np.nanmin(np.where(ok, X, np.nan), 0), 0)
        v, l, rr = _finish(Y, X, b, a, td[t], y[t], n, span, min_n, min_span)
        out["vel"][t], out["level"][t], out["resid"][t], out["n"][t], out["span"][t] = v, l, rr, n, span
    return out


ESTIMATORS = {"ols": ols, "theil_sen": theil_sen, "huber": huber}
