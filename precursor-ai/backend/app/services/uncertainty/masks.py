"""Deterministic data-quality masks. True = FLAGGED (unreliable or unusable for LOS interpretation). Not risk.

All thresholds are caller-supplied (no universal value exists) and must be recorded by the caller. NaN in any input
flags the cell: missing data is not usable data.

Geometry: `look_azimuth_deg` is the azimuth (clockwise from north) of the radar line of sight on the ground, pointing
from the sensor TOWARD the target; `incidence_deg` is the incidence angle at the ground. `aspect_deg` is the azimuth the
slope faces (downslope direction), clockwise from north; `slope_deg` is the slope angle from horizontal.
"""
import numpy as np


def low_coherence_mask(coherence: np.ndarray, threshold: float) -> np.ndarray:
    c = np.asarray(coherence, dtype=np.float64)
    return ~np.isfinite(c) | (c < threshold)


def vegetation_mask(ndvi: np.ndarray, threshold: float) -> np.ndarray:
    """Dense vegetation tends to decorrelate (esp. at C-band); flags NDVI >= threshold."""
    v = np.asarray(ndvi, dtype=np.float64)
    return ~np.isfinite(v) | (v >= threshold)


def _range_slope_rad(slope_deg, aspect_deg, look_azimuth_deg):
    """Slope angle in the range plane, positive when the terrain tilts TOWARD the sensor (faces it)."""
    s, a = np.radians(np.asarray(slope_deg, dtype=np.float64)), np.radians(np.asarray(aspect_deg, dtype=np.float64))
    toward_sensor = np.radians(look_azimuth_deg + 180.0)
    return np.arctan(np.tan(s) * np.cos(a - toward_sensor))


def layover_shadow_masks(slope_deg: np.ndarray, aspect_deg: np.ndarray, look_azimuth_deg: float, incidence_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """(layover, shadow). Layover: range slope facing the sensor >= incidence angle. Shadow: slope facing away >= 90 - incidence.
    Standard SAR geometry; local terrain only, no occlusion by distant relief."""
    alpha = np.degrees(_range_slope_rad(slope_deg, aspect_deg, look_azimuth_deg))
    bad = ~(np.isfinite(slope_deg) & np.isfinite(aspect_deg))
    return bad | (alpha >= incidence_deg), bad | (-alpha >= 90.0 - incidence_deg)


def los_sensitivity(slope_deg: np.ndarray, aspect_deg: np.ndarray, look_azimuth_deg: float, incidence_deg: float) -> np.ndarray:
    """Cosine between the unit ground-to-sensor vector and the unit downslope motion vector (slope-parallel sliding).
    1 = motion directly along LOS, 0 = motion perpendicular to LOS (invisible to InSAR). Sign: positive = toward sensor."""
    s, a = np.radians(np.asarray(slope_deg, dtype=np.float64)), np.radians(np.asarray(aspect_deg, dtype=np.float64))
    th, az = np.radians(incidence_deg), np.radians(look_azimuth_deg + 180.0)
    los = np.array([np.sin(th) * np.sin(az), np.sin(th) * np.cos(az), np.cos(th)])  # east, north, up (ground -> sensor)
    east, north, up = np.cos(s) * np.sin(a), np.cos(s) * np.cos(a), -np.sin(s)  # downslope motion
    sens = los[0] * east + los[1] * north + los[2] * up
    return np.where(np.asarray(slope_deg, dtype=np.float64) > 0, sens, np.nan)  # flat: aspect undefined, no downslope direction


def los_insensitive_mask(slope_deg, aspect_deg, look_azimuth_deg: float, incidence_deg: float, min_abs_sensitivity: float) -> np.ndarray:
    sens = los_sensitivity(slope_deg, aspect_deg, look_azimuth_deg, incidence_deg)
    return ~np.isfinite(sens) | (np.abs(sens) < min_abs_sensitivity)
