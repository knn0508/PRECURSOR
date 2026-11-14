"""Preliminary LOS velocity (mm/year). Not a time series and not a forecast (Phase 6).

Two supported cases, both strict about compatibility:
1. `interferogram_mean_velocity`: one interferogram's displacement divided by its own temporal baseline.
   This is an AVERAGE over the baseline, assumes steady motion, and ignores atmospheric and other errors.
2. `velocity_between_products`: two displacement products that share the SAME reference date and grid,
   differenced over the gap between their secondary dates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

DAYS_PER_YEAR = 365.25


class IncompatibleProducts(ValueError):
    pass


@dataclass(frozen=True)
class DisplacementMeta:
    reference_time: datetime | None
    secondary_time: datetime | None
    width: int
    height: int
    transform: tuple[float, ...]
    crs: str | None
    orbit_direction: str | None
    relative_orbit: int | None = None
    units: str = "mm"


def temporal_baseline_days(t_ref: datetime | None, t_sec: datetime | None) -> float:
    if t_ref is None or t_sec is None:
        raise IncompatibleProducts("acquisition date missing; cannot compute temporal baseline")
    dt = (t_sec - t_ref).total_seconds() / 86400.0
    if dt <= 0:
        raise IncompatibleProducts(f"secondary date is not after reference date (baseline {dt:.3f} d)")
    return dt


def interferogram_mean_velocity(displacement_mm: np.ndarray, t_ref: datetime | None, t_sec: datetime | None) -> np.ndarray:
    days = temporal_baseline_days(t_ref, t_sec)
    return np.asarray(displacement_mm, dtype=np.float64) / (days / DAYS_PER_YEAR)


def check_compatible(a: DisplacementMeta, b: DisplacementMeta) -> None:
    if a.units != b.units:
        raise IncompatibleProducts(f"units differ: {a.units} vs {b.units}")
    if (a.width, a.height) != (b.width, b.height):
        raise IncompatibleProducts("grid shapes differ")
    if not np.allclose(a.transform, b.transform, rtol=0, atol=1e-9 * max(1.0, abs(a.transform[0]))):
        raise IncompatibleProducts("grid geotransforms differ")
    if a.crs != b.crs:
        raise IncompatibleProducts(f"CRS differs: {a.crs} vs {b.crs}")
    if a.orbit_direction is None or a.orbit_direction != b.orbit_direction:
        raise IncompatibleProducts("viewing geometry (orbit direction) differs or is unknown")
    if a.relative_orbit != b.relative_orbit:
        raise IncompatibleProducts("relative orbit/track differs")
    if a.reference_time is None or a.reference_time != b.reference_time:
        raise IncompatibleProducts("products do not share the same reference date")


def velocity_between_products(
    earlier: np.ndarray, later: np.ndarray, a: DisplacementMeta, b: DisplacementMeta
) -> np.ndarray:
    """(later - earlier) / gap between secondary dates, in mm/year. Order is verified, not assumed."""
    check_compatible(a, b)
    gap = temporal_baseline_days(a.secondary_time, b.secondary_time)
    return (np.asarray(later, dtype=np.float64) - np.asarray(earlier, dtype=np.float64)) / (gap / DAYS_PER_YEAR)
