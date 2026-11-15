"""Deterministic indicators. Pure functions on numpy arrays; formulas in docs/scientific/TIME_SERIES_METHODOLOGY.md.

Statistical DESCRIPTION of observed values only. Nothing here extrapolates, forecasts, thresholds or labels risk. Every function
refuses (ShortSeriesError) below its stated minimum N instead of returning a weak number. t is in days; slopes are reported per
year (365.25 d). Confidence intervals assume independent errors: serial correlation makes them too narrow (stated in the output).
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

import numpy as np
from scipy import stats

from app.services.timeseries.types import (
    DAYS_PER_YEAR, MIN_N_ACCEL, MIN_N_LAG_PAIRS, MIN_N_MK, MIN_N_TREND, MIN_N_WINDOW, ShortSeriesError, TimeSeriesError)

INDEPENDENCE_CAVEAT = "interval assumes independent errors; serial correlation makes it too narrow"


def _need(n: int, minimum: int, what: str) -> None:
    if n < minimum:
        raise ShortSeriesError(f"{what} needs at least {minimum} valid observations, got {n}")


def linear_trend(t_days: np.ndarray, y: np.ndarray, alpha: float = 0.05) -> dict[str, Any]:
    """Ordinary least squares y = a + b t with a (1 - alpha) t-interval for the slope b."""
    t, y = np.asarray(t_days, float), np.asarray(y, float)
    _need(len(t), MIN_N_TREND, "linear trend")
    if np.ptp(t) == 0:
        raise TimeSeriesError("all observations share one time")
    r = stats.linregress(t, y)
    half = stats.t.ppf(1 - alpha / 2, len(t) - 2) * r.stderr
    k = DAYS_PER_YEAR
    return {"method": "ols", "n": len(t), "slope_per_year": r.slope * k, "slope_ci_per_year": [(r.slope - half) * k, (r.slope + half) * k],
            "confidence": 1 - alpha, "intercept": r.intercept, "r_squared": r.rvalue ** 2, "slope_stderr_per_year": r.stderr * k, "caveat": INDEPENDENCE_CAVEAT}


def theil_sen(t_days: np.ndarray, y: np.ndarray, alpha: float = 0.05) -> dict[str, Any]:
    """Theil-Sen median-of-pairwise-slopes estimator with scipy's confidence bounds (robust to outliers)."""
    t, y = np.asarray(t_days, float), np.asarray(y, float)
    _need(len(t), MIN_N_TREND, "Theil-Sen")
    if np.ptp(t) == 0:
        raise TimeSeriesError("all observations share one time")
    s, i, lo, hi = stats.theilslopes(y, t, alpha=1 - alpha)
    k = DAYS_PER_YEAR
    return {"method": "theil_sen", "n": len(t), "slope_per_year": s * k, "slope_ci_per_year": [lo * k, hi * k], "confidence": 1 - alpha, "intercept": i,
            "caveat": INDEPENDENCE_CAVEAT}


def mk_statistics(y: np.ndarray) -> tuple[float, float]:
    """Mann-Kendall S and its tie-corrected variance: Var(S) = [n(n-1)(2n+5) - sum_g t_g(t_g-1)(2t_g+5)] / 18."""
    y = np.asarray(y, float)
    n = len(y)
    s = float(sum(np.sign(y[j + 1:] - y[j]).sum() for j in range(n - 1)))
    _, counts = np.unique(y, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - float(np.sum(counts * (counts - 1) * (2 * counts + 5)))) / 18.0
    return s, var


def mann_kendall(y: np.ndarray, alpha: float = 0.05) -> dict[str, Any]:
    """Mann-Kendall monotonic-trend test on the values in time order (spacing is ignored). Z with continuity correction."""
    y = np.asarray(y, float)
    _need(len(y), MIN_N_MK, "Mann-Kendall")
    s, var = mk_statistics(y)
    if var <= 0:
        return {"method": "mann_kendall", "n": len(y), "s": s, "z": None, "p_value": None, "trend": "NOT_AVAILABLE", "reason": "all values tied"}
    z = 0.0 if s == 0 else (s - math.copysign(1, s)) / math.sqrt(var)
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    trend = "no_monotonic_trend_detected" if p >= alpha else ("increasing" if z > 0 else "decreasing")
    return {"method": "mann_kendall", "n": len(y), "s": s, "variance_s": var, "z": z, "p_value": p, "alpha": alpha, "trend": trend,
            "caveat": "assumes independent observations; serial correlation inflates significance; a detected trend is not a cause"}


def velocity_change(t_days: np.ndarray, y: np.ndarray, split_day: float, alpha: float = 0.05) -> dict[str, Any]:
    """Difference of OLS slopes before and after `split_day` (each window needs MIN_N_WINDOW points)."""
    t, y = np.asarray(t_days, float), np.asarray(y, float)
    a, b = t < split_day, t >= split_day
    _need(int(a.sum()), MIN_N_WINDOW, "velocity change (first window)")
    _need(int(b.sum()), MIN_N_WINDOW, "velocity change (second window)")
    ra, rb = stats.linregress(t[a], y[a]), stats.linregress(t[b], y[b])
    d = rb.slope - ra.slope
    se = math.hypot(ra.stderr, rb.stderr)
    df = int(a.sum() + b.sum() - 4)
    half = stats.t.ppf(1 - alpha / 2, df) * se
    k = DAYS_PER_YEAR
    return {"method": "ols_window_difference", "n_first": int(a.sum()), "n_second": int(b.sum()), "slope_first_per_year": ra.slope * k,
            "slope_second_per_year": rb.slope * k, "change_per_year": d * k, "change_ci_per_year": [(d - half) * k, (d + half) * k],
            "confidence": 1 - alpha, "split_day": split_day, "caveat": INDEPENDENCE_CAVEAT}


def acceleration(t_days: np.ndarray, y: np.ndarray, alpha: float = 0.05) -> dict[str, Any]:
    """Quadratic OLS y = c0 + c1 s + c2 s^2 (s in years, centred); acceleration = 2 c2 (units per year^2). Needs MIN_N_ACCEL points."""
    t, y = np.asarray(t_days, float), np.asarray(y, float)
    _need(len(t), MIN_N_ACCEL, "acceleration")
    s = (t - t.mean()) / DAYS_PER_YEAR
    x = np.column_stack([np.ones_like(s), s, s ** 2])
    if np.linalg.matrix_rank(x) < 3:
        raise TimeSeriesError("observation times do not support a quadratic fit")
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    df = len(t) - 3
    resid = y - x @ beta
    cov = (resid @ resid / df) * np.linalg.inv(x.T @ x)
    se = math.sqrt(cov[2, 2])
    half = stats.t.ppf(1 - alpha / 2, df) * se
    return {"method": "quadratic_ols", "n": len(t), "minimum_n": MIN_N_ACCEL, "acceleration_per_year2": 2 * beta[2],
            "acceleration_ci_per_year2": [2 * (beta[2] - half), 2 * (beta[2] + half)], "confidence": 1 - alpha, "caveat": INDEPENDENCE_CAVEAT}


# ---------------- rainfall indices (complete daily calendar required) ----------------
def _check_daily(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, float)
    if p.ndim != 1 or len(p) == 0:
        raise TimeSeriesError("daily rainfall must be a non-empty 1-D array on a complete daily calendar (missing days as NaN)")
    return p


def antecedent_sums(p: np.ndarray, windows: tuple[int, ...] = (1, 3, 7, 14, 30)) -> dict[int, np.ndarray]:
    """Trailing k-day accumulation ending on (and including) each day. NaN if any day in the window is missing: never partial sums."""
    p = _check_daily(p)
    out: dict[int, np.ndarray] = {}
    for k in windows:
        r = np.full(len(p), np.nan)
        for i in range(k - 1, len(p)):
            w = p[i - k + 1:i + 1]
            if np.isfinite(w).all():
                r[i] = w.sum()
        out[k] = r
    return out


def antecedent_precipitation_index(p: np.ndarray, k: float, spinup_days: int | None = None) -> np.ndarray:
    """API_t = k * API_(t-1) + P_t, 0 < k < 1 (caller-supplied recession constant; no default). The unknown initial state is taken as 0,
    so the first `spinup_days` (default ceil(ln 0.01 / ln k), i.e. the initial value weighs < 1%) are NaN. A missing day makes the state
    unknown: NaN until `spinup_days` further valid days have passed."""
    p = _check_daily(p)
    if not 0 < k < 1:
        raise TimeSeriesError("recession constant k must be in (0, 1)")
    spin = math.ceil(math.log(0.01) / math.log(k)) if spinup_days is None else spinup_days
    out = np.full(len(p), np.nan)
    state, run = 0.0, 0
    for i, v in enumerate(p):
        if not math.isfinite(v):
            run = 0
            state = 0.0
            continue
        state = k * state + v
        run += 1
        if run > spin:
            out[i] = state
    return out


def storm_events(p: np.ndarray, start: date, wet_threshold_mm: float) -> dict[str, Any]:
    """Descriptive wet spells: maximal runs of consecutive days with P >= wet_threshold_mm. The threshold is a caller convention to
    define a wet day (for example 1 mm/day), NOT an alert level. Daily resolution: this is not storm-scale intensity."""
    p = _check_daily(p)
    events, i = [], 0
    while i < len(p):
        if np.isfinite(p[i]) and p[i] >= wet_threshold_mm:
            j = i
            while j + 1 < len(p) and np.isfinite(p[j + 1]) and p[j + 1] >= wet_threshold_mm:
                j += 1
            seg = p[i:j + 1]
            events.append({"start": (date.fromordinal(start.toordinal() + i)).isoformat(), "end": (date.fromordinal(start.toordinal() + j)).isoformat(),
                           "duration_days": j - i + 1, "total_mm": float(seg.sum()), "peak_mm_day": float(seg.max()),
                           "adjacent_to_missing_day": bool((i > 0 and not np.isfinite(p[i - 1])) or (j + 1 < len(p) and not np.isfinite(p[j + 1])))})
            i = j + 1
        else:
            i += 1
    return {"wet_day_threshold_mm": wet_threshold_mm, "n_events": len(events), "events": events, "missing_days": int((~np.isfinite(p)).sum()),
            "peak_mm_day": max((e["peak_mm_day"] for e in events), default=None),
            "caveat": "descriptive statistics of observed daily values; the threshold is a definition of a wet day, not an alert level"}


def lagged_correlation(x_days: np.ndarray, x: np.ndarray, y_days: np.ndarray, y: np.ndarray, lags: list[int]) -> dict[str, Any]:
    """DESCRIPTIVE Pearson r between x(d) and y(d + lag) using only EXACT day matches (no interpolation). Days are integer day numbers.
    A lag with fewer than MIN_N_LAG_PAIRS pairs, or a constant series, is NOT_AVAILABLE. No p-values: serial correlation invalidates them."""
    xs = {int(d): float(v) for d, v in zip(x_days, x) if np.isfinite(v)}
    ys = {int(d): float(v) for d, v in zip(y_days, y) if np.isfinite(v)}
    res = []
    for lag in lags:
        pairs = [(v, ys[d + lag]) for d, v in xs.items() if d + lag in ys]
        if len(pairs) < MIN_N_LAG_PAIRS:
            res.append({"lag_days": lag, "n_pairs": len(pairs), "status": "NOT_AVAILABLE", "reason": f"fewer than {MIN_N_LAG_PAIRS} exact-date pairs"})
            continue
        a, b = np.array(pairs).T
        if np.ptp(a) == 0 or np.ptp(b) == 0:
            res.append({"lag_days": lag, "n_pairs": len(pairs), "status": "NOT_AVAILABLE", "reason": "constant series"})
            continue
        res.append({"lag_days": lag, "n_pairs": len(pairs), "status": "DONE", "pearson_r": float(np.corrcoef(a, b)[0, 1])})
    return {"method": "lagged_pearson_exact_dates", "lags": res,
            "caveat": "correlation is not causation; shared seasonality and serial correlation can produce any lag; no significance is claimed"}
