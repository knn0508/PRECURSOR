"""Aspect and circular statistics.

CONVENTION: aspect is the compass direction the surface FACES, i.e. the DOWNSLOPE direction, in degrees CLOCKWISE FROM
NORTH in [0, 360): 0 = N, 90 = E, 180 = S, 270 = W. A plane descending toward the east has aspect 90.
Derivation: downslope vector = -(grad z) = (east: -dz/dx, north: -dz/dy); aspect = atan2(east, north) mod 360.
Flat cells (slope < FLAT_EPS_DEG) have no direction: they are NaN (counted), never 0 or -1.
Aspect is circular: averages must use sin/cos (see circular_mean_deg), never the arithmetic mean of degrees.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from affine import Affine

from app.services.environmental.dem.slope import slope_from_gradients, terrain_gradients

FLAT_EPS_DEG = 1e-3  # documented epsilon: slopes below this are treated as flat (aspect undefined)
SECTOR_LABELS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


@dataclass
class AspectResult:
    aspect: np.ndarray  # float32 degrees, NaN for flat/undefined
    flat_count: int  # cells with a valid slope below the epsilon
    valid_count: int  # cells with a defined aspect


def aspect_from_gradients(gx: np.ndarray, gy: np.ndarray, flat_eps_deg: float = FLAT_EPS_DEG) -> AspectResult:
    with np.errstate(invalid="ignore"):
        slope = slope_from_gradients(gx, gy)
        valid = np.isfinite(slope)
        flat = valid & (slope < flat_eps_deg)
        asp = np.rad2deg(np.arctan2(-gx.astype(np.float64), -gy.astype(np.float64)))
        asp = np.mod(asp, 360.0).astype(np.float32)
    asp[asp >= 360.0] = 0.0  # float32 rounding can land exactly on 360
    asp[~valid | flat] = np.nan
    return AspectResult(asp, int(flat.sum()), int(np.isfinite(asp).sum()))


def aspect_degrees(z: np.ndarray, crs: str, transform: Affine, flat_eps_deg: float = FLAT_EPS_DEG) -> AspectResult:
    return aspect_from_gradients(*terrain_gradients(z, crs, transform), flat_eps_deg=flat_eps_deg)


def classify_8(aspect: np.ndarray) -> np.ndarray:
    """Sector index 0..7 (N,NE,E,SE,S,SW,W,NW; sectors centred on the cardinal/intercardinal directions); -1 = no aspect."""
    a = np.asarray(aspect, dtype=np.float64)
    ok = np.isfinite(a)
    out = np.full(a.shape, -1, dtype=np.int8)
    out[ok] = (np.floor(np.mod(a[ok] + 22.5, 360.0) / 45.0)).astype(np.int8) % 8
    return out


def _components(deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    d = np.asarray(deg, dtype=np.float64).ravel()
    d = d[np.isfinite(d)]
    return np.sin(np.deg2rad(d)), np.cos(np.deg2rad(d))


def resultant_length(deg: np.ndarray) -> float | None:
    """Mean resultant length R in [0,1]: 1 = all identical directions, ~0 = uniformly spread. None if no data."""
    s, c = _components(deg)
    return None if s.size == 0 else float(np.hypot(s.mean(), c.mean()))


def circular_mean_deg(deg: np.ndarray) -> float | None:
    """Circular mean in [0,360). None if no data or the directions cancel (R ~ 0, mean undefined)."""
    s, c = _components(deg)
    if s.size == 0 or np.hypot(s.mean(), c.mean()) < 1e-9:
        return None
    return float(np.mod(np.rad2deg(np.arctan2(s.mean(), c.mean())), 360.0))


def circular_std_deg(deg: np.ndarray) -> float | None:
    """Circular standard deviation sqrt(-2 ln R) in degrees (Mardia). None if no data; inf if R == 0."""
    r = resultant_length(deg)
    if r is None:
        return None
    return float("inf") if r <= 0 else float(np.rad2deg(np.sqrt(-2.0 * np.log(min(r, 1.0)))))


def sector_histogram(aspect: np.ndarray) -> dict[str, int]:
    idx = classify_8(aspect)
    return {lab: int((idx == k).sum()) for k, lab in enumerate(SECTOR_LABELS)}
