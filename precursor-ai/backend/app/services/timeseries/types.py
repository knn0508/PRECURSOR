"""Phase 6 time-series types. Chronological ordering is mandatory and the mixed-geometry guard lives here, so no series
can exist that violates either rule. Missing values are None/NaN and are never filled."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

DAYS_PER_YEAR = 365.25

# kind -> units. LOS kinds are line-of-sight measurements (not vertical, sign convention unverified: Phase 3 issue 14).
KINDS = {
    "los_displacement_mm": "mm",
    "los_velocity_mm_yr": "mm/yr",
    "coherence": "1",
    "rainfall_mm_day": "mm/day",
    "soil_moisture": "m3/m3",
}
GEOMETRY_KINDS = {"los_displacement_mm", "los_velocity_mm_yr", "coherence"}

# Minimum numbers of VALID observations. Working choices (not literature-derived); each indicator refuses below its N.
MIN_N_TREND = 5  # OLS / Theil-Sen: n - 2 >= 3 degrees of freedom for the OLS interval
MIN_N_MK = 10  # Mann-Kendall normal approximation is conventionally used from about n = 10
MIN_N_ACCEL = 8  # quadratic fit: n - 3 >= 5 degrees of freedom
MIN_N_WINDOW = 5  # each window in a velocity-change comparison
MIN_N_LAG_PAIRS = 10  # paired observations per lag in the descriptive cross-correlation


class TimeSeriesError(ValueError):
    pass


class ShortSeriesError(TimeSeriesError):
    """Too few valid observations for the requested indicator."""


class MixedGeometryError(TimeSeriesError):
    """Ascending/descending LOS, different tracks or different sensors in one series."""


@dataclass(frozen=True)
class SeriesPoint:
    time: datetime  # timezone-aware
    value: float | None
    source: str  # e.g. "NISAR GUNW", "GPM IMERG", "SMAP SPL3SMP_E", "SYNTHETIC"
    sensor: str
    synthetic: bool
    quality: float | None = None  # e.g. coherence 0-1 for a deformation point; None = not recorded
    track: int | None = None
    orbit_direction: str | None = None  # ASCENDING | DESCENDING
    look_direction: str | None = None  # LEFT | RIGHT


@dataclass
class TimeSeries:
    kind: str
    zone: str  # AOI / zone / pixel identifier (free text, stored with the series)
    points: list[SeriesPoint]
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise TimeSeriesError(f"unknown series kind {self.kind!r}; known: {sorted(KINDS)}")
        if not self.points:
            raise TimeSeriesError("a series needs at least one point")
        for p in self.points:
            if p.time.tzinfo is None:
                raise TimeSeriesError("point times must be timezone-aware (no assumed time zone)")
        times = [p.time for p in self.points]
        if any(b <= a for a, b in zip(times, times[1:])):
            raise TimeSeriesError("points must be strictly chronological (no duplicates, no reordering is done for you)")
        if len({p.sensor for p in self.points}) != 1:
            raise MixedGeometryError("a series may not mix sensors; keep one series per sensor")
        if self.kind in GEOMETRY_KINDS:
            geo = {(p.orbit_direction, p.track, p.look_direction) for p in self.points}
            if len(geo) != 1 or None in next(iter(geo))[:2]:
                raise MixedGeometryError(
                    "LOS series need one (orbit direction, track, look direction) for all points; ascending and descending are never "
                    "merged (no decomposition is implemented)")
        self.points = [p if p.value is None or math.isfinite(p.value) else SeriesPoint(**{**p.__dict__, "value": None}) for p in self.points]

    @property
    def units(self) -> str:
        return KINDS[self.kind]

    @property
    def contains_synthetic(self) -> bool:
        return any(p.synthetic for p in self.points)

    def valid(self) -> tuple[np.ndarray, np.ndarray]:
        """(days since the first point, values) of the non-missing points only."""
        t0 = self.points[0].time
        v = [(((p.time - t0).total_seconds()) / 86400.0, p.value) for p in self.points if p.value is not None]
        return np.array([a for a, _ in v], dtype=float), np.array([b for _, b in v], dtype=float)

    def meta(self) -> dict[str, Any]:
        p0 = self.points[0]
        return {"kind": self.kind, "units": self.units, "zone": self.zone, "sensor": p0.sensor, "sources": sorted({p.source for p in self.points}),
                "orbit_direction": p0.orbit_direction, "track": p0.track, "look_direction": p0.look_direction,
                "first_time": self.points[0].time.isoformat(), "last_time": self.points[-1].time.isoformat(),
                "contains_synthetic_data": self.contains_synthetic, "real_data_validation": "NOT_PERFORMED"}
