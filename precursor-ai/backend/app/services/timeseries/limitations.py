"""Per-series limitations report: what the sampling allows, before any indicator is read."""
from __future__ import annotations

import numpy as np

from app.services.timeseries.types import TimeSeries


def limitations(series: TimeSeries, *, gap_factor: float = 2.0, min_period_days: float | None = None) -> dict:
    """gap = interval between consecutive VALID observations longer than gap_factor x the median interval (factor is a caller choice).
    Aliasing: a period shorter than twice the median interval cannot be resolved; assessed only when `min_period_days` is given."""
    t, _ = series.valid()
    n, n_valid = len(series.points), len(t)
    rep: dict = {"n_points": n, "n_valid": n_valid, "missing_fraction": 1 - n_valid / n, "span_days": float(t[-1] - t[0]) if n_valid > 1 else None,
                 "median_interval_days": None, "max_interval_days": None, "interval_cv": None, "gaps": [], "gap_factor": gap_factor,
                 "aliasing": "NOT_ASSESSED", "min_period_days": min_period_days,
                 "notes": ["gaps are reported, never filled or interpolated",
                           *(["series contains SYNTHETIC data"] if series.contains_synthetic else [])]}
    if n_valid < 2:
        rep["notes"].append("fewer than 2 valid observations: no interval statistics")
        return rep
    dt = np.diff(t)
    med = float(np.median(dt))
    rep.update(median_interval_days=med, max_interval_days=float(dt.max()), interval_cv=float(dt.std() / dt.mean()) if dt.mean() else None)
    t0 = series.points[0].time
    rep["gaps"] = [{"after": (t0.fromtimestamp(t0.timestamp() + float(t[i]) * 86400, t0.tzinfo)).isoformat(), "interval_days": float(dt[i])}
                   for i in range(len(dt)) if dt[i] > gap_factor * med]
    if min_period_days is not None:
        rep["aliasing"] = "POSSIBLE" if 2 * med > min_period_days else "NOT_INDICATED"
    return rep
