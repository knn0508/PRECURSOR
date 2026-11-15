"""SYNTHETIC series for tests and demos. Always flagged synthetic with sensor SYNTHETIC; never presented as observations."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from app.services.timeseries.types import SeriesPoint, TimeSeries

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def synthetic_los_series(days: list[float], *, slope_mm_yr: float, noise_mm: float = 0.0, seed: int = 0, quad_mm_yr2: float = 0.0,
                         kind: str = "los_displacement_mm", zone: str = "synthetic-zone", orbit_direction: str = "ASCENDING", track: int = 1,
                         nan_at: tuple[int, ...] = ()) -> TimeSeries:
    rng = np.random.default_rng(seed)
    pts = []
    for i, d in enumerate(days):
        yr = d / 365.25
        v = slope_mm_yr * yr + 0.5 * quad_mm_yr2 * yr ** 2 + (rng.normal(0, noise_mm) if noise_mm else 0.0)
        pts.append(SeriesPoint(time=T0 + timedelta(days=d), value=None if i in nan_at else float(v), source="SYNTHETIC", sensor="SYNTHETIC", synthetic=True,
                               quality=0.8, track=track, orbit_direction=orbit_direction, look_direction="RIGHT"))
    return TimeSeries(kind=kind, zone=zone, points=pts, notes=["SYNTHETIC TEST DATA: not a satellite observation"])


def synthetic_rainfall(values: list[float | None], zone: str = "synthetic-zone") -> TimeSeries:
    pts = [SeriesPoint(time=T0 + timedelta(days=i), value=v, source="SYNTHETIC", sensor="SYNTHETIC", synthetic=True) for i, v in enumerate(values)]
    return TimeSeries(kind="rainfall_mm_day", zone=zone, points=pts, notes=["SYNTHETIC TEST DATA: not a satellite observation"])
