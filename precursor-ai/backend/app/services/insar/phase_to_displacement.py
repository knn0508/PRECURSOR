"""Unwrapped interferometric phase -> line-of-sight (LOS) displacement.

    d_LOS = -(lambda / 4*pi) * delta_phi          (this module's convention)

* `delta_phi` is UNWRAPPED, DIFFERENTIAL interferometric phase in radians (topography and orbit effects
  already removed by the producing processor). Applying this to anything else is invalid.
* d_LOS is the change in sensor-to-ground range direction along the radar line of sight, in METRES here
  (converted to millimetres by the caller). Under this convention a positive value is displacement TOWARD
  the satellite (range decrease). Another producer may define phase with the opposite sign: the sign of the
  output is only as correct as that assumption. `SIGN_CONVENTION_VERIFIED` stays False until the sign has been
  checked against real data of a known-motion site.
* LOS displacement is one component of 3D motion. It is NOT vertical or horizontal displacement.
* Unwrapped phase is relative: no reference point is applied here, so values are only meaningful as differences.
"""
from __future__ import annotations

import math

import numpy as np

SIGN_CONVENTION = "d_LOS = -(lambda/4pi) * unwrapped_phase; positive = toward satellite (assumed, NOT verified)"
SIGN_CONVENTION_VERIFIED = False
SPEED_OF_LIGHT_M_S = 299_792_458.0
# Radar bands span ~ P-band (0.7 m) to Ka-band (0.008 m); anything outside is certainly a unit error.
_WAVELENGTH_RANGE_M = (0.005, 1.0)


def wavelength_from_frequency(frequency_hz: float) -> float:
    if not math.isfinite(frequency_hz) or frequency_hz <= 0:
        raise ValueError(f"invalid radar centre frequency: {frequency_hz!r}")
    return validate_wavelength(SPEED_OF_LIGHT_M_S / frequency_hz)


def validate_wavelength(wavelength_m: float) -> float:
    lo, hi = _WAVELENGTH_RANGE_M
    if not math.isfinite(wavelength_m) or not (lo <= wavelength_m <= hi):
        raise ValueError(f"radar wavelength {wavelength_m!r} m outside plausible range {lo}-{hi} m (unit error?)")
    return float(wavelength_m)


def phase_to_los_displacement_m(phase_rad: np.ndarray, wavelength_m: float) -> np.ndarray:
    """Element-wise conversion. NaN/inf stay NaN (missing is never turned into zero displacement)."""
    wavelength_m = validate_wavelength(wavelength_m)
    phase = np.asarray(phase_rad, dtype=np.float64)
    out = -(wavelength_m / (4.0 * math.pi)) * phase
    out[~np.isfinite(out)] = np.nan
    return out


def phase_per_displacement_rad_per_m(wavelength_m: float) -> float:
    """One full fringe (2*pi rad) equals lambda/2 of LOS displacement; handy for sanity checks."""
    return 4.0 * math.pi / validate_wavelength(wavelength_m)
