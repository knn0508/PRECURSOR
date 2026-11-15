"""Lead-time values for one reference date (building blocks for the Phase 5 reserved `dyn__*__t_minus_{k}d` columns).

These work on ONE series. Phase 4 stores AOI-level series only, so they give AOI-level values; assigning them to per-point dataset rows
would make a spatially constant feature and is NOT done (the Phase 5 columns stay NOT_AVAILABLE). Missing is NaN, never zero.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from app.services.timeseries.types import TimeSeries


def rainfall_before(series: TimeSeries, reference: date, k: int) -> float:
    """Accumulation over the k days [reference-k, reference-1]; the reference day itself is excluded (it may be post-event). NaN if any day
    is missing or outside the series."""
    if series.kind != "rainfall_mm_day":
        raise ValueError("rainfall_before needs a rainfall_mm_day series")
    by_day = {p.time.date(): p.value for p in series.points}
    vals = [by_day.get(reference - timedelta(days=i)) for i in range(1, k + 1)]
    return float(sum(vals)) if all(v is not None for v in vals) else float("nan")


def value_at_lead(series: TimeSeries, reference: date, k: int, max_age_days: float) -> float:
    """Latest valid observation at or before reference-k and no older than `max_age_days` (caller-set); NaN otherwise. No interpolation."""
    cutoff = reference - timedelta(days=k)
    cands = [p for p in series.points if p.value is not None and p.time.date() <= cutoff and (cutoff - p.time.date()).days <= max_age_days]
    return float(cands[-1].value) if cands else float("nan")


__all__ = ["rainfall_before", "value_at_lead", "np"]
