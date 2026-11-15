"""Series analysis: limitations report plus every applicable indicator, each either a result or NOT_AVAILABLE with the reason."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

import numpy as np

from app.services.timeseries import indicators as ind
from app.services.timeseries.limitations import limitations
from app.services.timeseries.types import GEOMETRY_KINDS, TimeSeries, TimeSeriesError


def _try(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return fn()
    except TimeSeriesError as exc:  # includes ShortSeriesError
        return {"status": "NOT_AVAILABLE", "reason": str(exc)}


def analyze(series: TimeSeries, *, alpha: float = 0.05, gap_factor: float = 2.0, min_period_days: float | None = None,
            wet_threshold_mm: float = 1.0, api_k: float | None = None) -> dict[str, Any]:
    t, y = series.valid()
    out: dict[str, Any] = {
        "series": series.meta(), "limitations": limitations(series, gap_factor=gap_factor, min_period_days=min_period_days),
        "indicators": {"linear_trend": _try(lambda: ind.linear_trend(t, y, alpha)), "theil_sen": _try(lambda: ind.theil_sen(t, y, alpha)),
                       "mann_kendall": _try(lambda: ind.mann_kendall(y, alpha)), "acceleration": _try(lambda: ind.acceleration(t, y, alpha))},
        "generated_at": datetime.now(UTC).isoformat(), "real_data_validation": "NOT_PERFORMED", "contains_synthetic_data": series.contains_synthetic,
        "notes": ["Descriptive statistics of observed values. No forecast, no extrapolation, no risk label."]}
    if series.kind in GEOMETRY_KINDS:
        out["notes"].append("LOS measurement along one fixed geometry; not vertical motion; sign convention unverified (Phase 3 issue 14).")
    if series.kind == "rainfall_mm_day":
        p0 = series.points[0].time
        days = np.array([(p.time - p0).days for p in series.points])
        if (np.diff(days) == 1).all():
            p = np.array([np.nan if q.value is None else q.value for q in series.points], float)
            out["rainfall"] = {"antecedent_sums_last_value": {str(k): (None if np.isnan(v[-1]) else float(v[-1])) for k, v in ind.antecedent_sums(p).items()},
                               "storm_events": ind.storm_events(p, p0.date(), wet_threshold_mm)}
            if api_k is not None:
                a = ind.antecedent_precipitation_index(p, api_k)
                out["rainfall"]["api_last_value"] = None if np.isnan(a[-1]) else float(a[-1])
                out["rainfall"]["api_k"] = api_k
        else:
            out["rainfall"] = {"status": "NOT_AVAILABLE", "reason": "rainfall indices need a complete daily calendar (missing days as null)"}
    return out
