"""Explicit unit / sign / time / sensor-comparison guards (skill Step 4 and mandatory tests).

Every conversion is explicit and fails loudly on anything unexpected, so unit and sign errors cannot
pass silently. Sensor comparisons are refused until geometry, sign and timing have been verified.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LENGTH_TO_MM = {"meters": 1000.0, "meter": 1000.0, "m": 1000.0, "millimeters": 1.0, "millimeter": 1.0, "mm": 1.0}


def to_mm(values, units: str) -> np.ndarray:
    """Length -> mm. Raises for radians or unknown units (phase needs phase_to_los_mm)."""
    key = str(units).strip().lower()
    if key not in LENGTH_TO_MM:
        raise ValueError(f"unsupported length unit {units!r}; phase in radians must go through phase_to_los_mm")
    return np.asarray(values, dtype=np.float64) * LENGTH_TO_MM[key]


def phase_to_los_mm(phase_rad, wavelength_m: float, sign: int) -> np.ndarray:
    """Unwrapped interferometric phase -> LOS path change in mm: sign * phase * lambda / (4 pi).

    `sign` must be +1 or -1 and must come from the product's documented convention. No default is
    given on purpose, so an unverified sign cannot be used silently.
    """
    if sign not in (1, -1):
        raise ValueError("sign must be +1 or -1 and taken from the product specification")
    if not (0.01 < float(wavelength_m) < 1.0):
        raise ValueError(f"implausible radar wavelength {wavelength_m} m")
    return sign * np.asarray(phase_rad, dtype=np.float64) * float(wavelength_m) / (4 * np.pi) * 1000.0


def assert_time_order(times) -> pd.DatetimeIndex:
    """Acquisition times must be strictly increasing (catches shuffled or duplicated dates)."""
    t = pd.DatetimeIndex(times)
    if len(t) > 1 and not (np.diff(t.values.astype("datetime64[s]").astype(np.int64)) > 0).all():
        raise ValueError("acquisition times are not strictly increasing (shuffled, duplicated or shifted?)")
    return t


class SensorComparisonError(RuntimeError):
    pass


REQUIRED_CHECKS = ("same_los_geometry_or_projected", "sign_convention_verified", "units_verified",
                   "time_windows_overlap")


def check_sensor_comparison(checks: dict, time_a: tuple, time_b: tuple, max_offset_days: float = 6.0) -> None:
    """Refuse a value-level OPERA <-> NISAR comparison unless every requirement is satisfied.

    checks: dict of REQUIRED_CHECKS -> bool (set only from verified metadata / documentation).
    time_a, time_b: (start, end) of each measurement window; the windows must overlap within tolerance.
    """
    missing = [k for k in REQUIRED_CHECKS if k != "time_windows_overlap" and not checks.get(k, False)]
    a0, a1 = (pd.Timestamp(x) for x in time_a)
    b0, b1 = (pd.Timestamp(x) for x in time_b)
    tol = pd.Timedelta(days=max_offset_days)
    overlap = (abs(a0 - b0) <= tol) and (abs(a1 - b1) <= tol)
    if not overlap:
        missing.append(f"time_windows_overlap ({a0.date()}..{a1.date()} vs {b0.date()}..{b1.date()})")
    if missing:
        raise SensorComparisonError("value-level sensor comparison refused; unverified: " + ", ".join(missing))
