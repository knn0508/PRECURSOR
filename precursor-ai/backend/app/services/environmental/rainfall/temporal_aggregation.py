"""Daily calendar, monthly and rolling accumulations. Pure pandas/numpy, no I/O.

Rules: a missing day is NaN, NEVER zero. An accumulation exists only if EVERY day it covers is observed.
No interpolation, no gap filling, no forecasting. Daily-product values are mm/day ACCUMULATIONS already
(a mm/hr RATE is a different quantity: see rate_to_accumulation_mm).
"""
from __future__ import annotations

from datetime import date as Date
from typing import Any, Iterable

import numpy as np
import pandas as pd

from app.services.environmental.types import EnvError

DEFAULT_WINDOWS = (3, 7, 30)


def rate_to_accumulation_mm(rate_mm_per_hr: float | np.ndarray, step_hours: float = 0.5) -> float | np.ndarray:
    """Accumulation (mm) of ONE time step from a precipitation RATE (mm/hr): rate x step length.
    A half-hourly IMERG rate needs x0.5 h per step. NOT used by the daily pipeline."""
    if step_hours <= 0:
        raise EnvError("step_hours must be > 0")
    return np.asarray(rate_mm_per_hr, dtype=float) * step_hours if not np.isscalar(rate_mm_per_hr) \
        else float(rate_mm_per_hr) * step_hours


def build_daily_series(observations: Iterable[tuple[Date, float | None]], start: Date, end: Date
                       ) -> tuple[pd.DataFrame, list[str]]:
    """Complete calendar start..end (inclusive). Columns: precip_mm_day (float, NaN when missing), observed (bool).

    Dates outside the window are ignored with a warning. Duplicate dates: identical values are collapsed with a
    warning; DIFFERENT values raise EnvError (no silent choice)."""
    if end < start:
        raise EnvError("end date precedes start date")
    cal = pd.date_range(start, end, freq="D")
    warns: list[str] = []
    seen: dict[Date, float | None] = {}
    for d, v in observations:
        if d < start or d > end:
            warns.append(f"date {d.isoformat()} outside window {start}..{end}: ignored")
            continue
        v = None if v is None or not np.isfinite(v) else float(v)
        if d in seen:
            if seen[d] != v:
                raise EnvError(f"duplicate date {d.isoformat()} with different values ({seen[d]} vs {v})")
            warns.append(f"duplicate date {d.isoformat()} with identical value: counted once")
            continue
        seen[d] = v
    s = pd.Series(np.nan, index=cal, name="precip_mm_day", dtype="float64")
    for d, v in seen.items():
        if v is not None:
            s.loc[pd.Timestamp(d)] = v
    df = s.to_frame()
    df["observed"] = df["precip_mm_day"].notna()
    df.index.name = "date"
    return df, warns


def monthly_accumulation(daily: pd.DataFrame) -> pd.DataFrame:
    """Per calendar month: sum_mm only when ALL days of the month (full calendar month, incl. days outside the
    requested window) are observed; otherwise NaN with observed_days/expected_days reported."""
    g = daily.groupby(daily.index.to_period("M"))
    out = pd.DataFrame({
        "observed_days": g["observed"].sum().astype(int),
        "expected_days": [p.days_in_month for p in g.size().index],
        "sum_mm": g["precip_mm_day"].sum(min_count=1),
    })
    out["complete"] = out["observed_days"] == out["expected_days"]
    out.loc[~out["complete"], "sum_mm"] = np.nan
    out.index = out.index.astype(str)
    out.index.name = "month"
    return out


def rolling_accumulation(daily: pd.DataFrame, windows: Iterable[int] = DEFAULT_WINDOWS) -> pd.DataFrame:
    """Trailing-window sums (mm) ending on each date; NaN unless the whole window is observed (min_periods=window)."""
    out = pd.DataFrame(index=daily.index)
    for w in windows:
        if int(w) < 1:
            raise EnvError("rolling window must be >= 1 day")
        out[f"sum_{int(w)}d_mm"] = daily["precip_mm_day"].rolling(int(w), min_periods=int(w)).sum()
    return out


def missing_ranges(daily: pd.DataFrame) -> list[dict[str, Any]]:
    """Contiguous runs of missing days as [{start, end, days}] (ISO dates)."""
    miss = ~daily["observed"].to_numpy()
    out: list[dict[str, Any]] = []
    i, n = 0, len(miss)
    while i < n:
        if miss[i]:
            j = i
            while j + 1 < n and miss[j + 1]:
                j += 1
            out.append({"start": daily.index[i].date().isoformat(), "end": daily.index[j].date().isoformat(),
                        "days": j - i + 1})
            i = j + 1
        else:
            i += 1
    return out


def summary_counts(daily: pd.DataFrame) -> dict[str, Any]:
    obs = daily.index[daily["observed"]]
    return {
        "expected_days": int(len(daily)), "observed_days": int(daily["observed"].sum()),
        "missing_days": int((~daily["observed"]).sum()),
        "first_observed": obs[0].date().isoformat() if len(obs) else None,
        "last_observed": obs[-1].date().isoformat() if len(obs) else None,
        "missing_ranges": missing_ranges(daily),
    }


def _num(x: float) -> float | None:
    return None if x is None or not np.isfinite(x) else float(x)


def series_to_records(daily: pd.DataFrame, rolling: pd.DataFrame, monthly: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    """JSON-safe plain lists (NaN -> None)."""
    d = [{"date": ts.date().isoformat(), "precip_mm_day": _num(r.precip_mm_day), "observed": bool(r.observed)}
         for ts, r in daily.iterrows()]
    r_ = [{"date": ts.date().isoformat(), **{c: _num(v) for c, v in row.items()}} for ts, row in rolling.iterrows()]
    m = [{"month": str(k), "observed_days": int(r.observed_days), "expected_days": int(r.expected_days),
          "complete": bool(r.complete), "sum_mm": _num(r.sum_mm)} for k, r in monthly.iterrows()]
    return {"daily": d, "rolling": r_, "monthly": m}
