"""Slope by the Horn (1981) 3x3 method in numpy, with correct metric cell sizes.

Neighbourhood (row 0 = north):      a b c        dz/dx (east+)  = ((c + 2f + i) - (a + 2d + g)) / (8 dx)
                                    d e f        dz/dy (north+) = ((a + 2b + c) - (g + 2h + i)) / (8 dy)
                                    g h i        slope = atan(hypot(dz/dx, dz/dy))

Cell size in METRES: for a geographic CRS dx = N(phi) cos(phi) dlon and dy = M(phi) dphi per row (phi = row-centre
latitude, M/N = meridian/prime-vertical radii of curvature of the CRS ellipsoid), so degrees are never treated as metres.
For a projected CRS the CRS linear unit is converted to metres (feet included). Any NaN in the 3x3 window, a NaN centre
and the one-pixel border all give NaN (never zero). Processed in row bands to bound temporaries.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

import numpy as np
from affine import Affine
from pyproj import CRS

from app.services.environmental.types import EnvError


def cell_sizes_m(crs: str, transform: Affine, height: int) -> tuple[np.ndarray, np.ndarray]:
    """Per-row (dx_m, dy_m) arrays of length `height`. Requires a north-up, non-rotated grid."""
    if transform.b != 0 or transform.d != 0:
        raise EnvError("rotated/sheared grids are not supported for slope")
    if not crs:
        raise EnvError("CRS missing; cell size in metres cannot be determined")
    c = CRS.from_user_input(crs)
    if c.is_geographic:
        ell = c.ellipsoid
        a, b = ell.semi_major_metre, ell.semi_minor_metre
        e2 = 1.0 - (b / a) ** 2
        lat = np.deg2rad(transform.f + (np.arange(height) + 0.5) * transform.e)
        w = 1.0 - e2 * np.sin(lat) ** 2
        n_rad, m_rad = a / np.sqrt(w), a * (1.0 - e2) / w ** 1.5
        return n_rad * np.cos(lat) * np.deg2rad(abs(transform.a)), m_rad * np.deg2rad(abs(transform.e))
    if not c.is_projected:
        raise EnvError("CRS is neither geographic nor projected; cannot derive metric cell size")
    f = c.axis_info[0].unit_conversion_factor  # metres per CRS unit (0.3048 for international foot)
    if not f or f <= 0:
        raise EnvError("CRS linear unit unknown")
    return np.full(height, abs(transform.a) * f), np.full(height, abs(transform.e) * f)


def horn_gradients(z: np.ndarray, dx: np.ndarray, dy: np.ndarray, band_rows: int = 512) -> tuple[np.ndarray, np.ndarray]:
    """(dz/dx east-positive, dz/dy north-positive) as float32 (m/m), NaN on the border and wherever the window has NaN."""
    h, w = z.shape
    gx = np.full((h, w), np.nan, dtype=np.float32)
    gy = np.full((h, w), np.nan, dtype=np.float32)
    if h < 3 or w < 3:
        return gx, gy
    for r0 in range(1, h - 1, band_rows):
        r1 = min(r0 + band_rows, h - 1)
        b = z[r0 - 1:r1 + 1].astype(np.float64)
        a, bb, c = b[:-2, :-2], b[:-2, 1:-1], b[:-2, 2:]
        d, e, f = b[1:-1, :-2], b[1:-1, 1:-1], b[1:-1, 2:]
        g, hh, i = b[2:, :-2], b[2:, 1:-1], b[2:, 2:]
        with np.errstate(invalid="ignore"):
            sx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * dx[r0:r1, None])
            sy = ((a + 2 * bb + c) - (g + 2 * hh + i)) / (8 * dy[r0:r1, None])
        bad = ~(np.isfinite(sx) & np.isfinite(sy) & np.isfinite(e))
        sx[bad] = np.nan
        sy[bad] = np.nan
        gx[r0:r1, 1:-1] = sx
        gy[r0:r1, 1:-1] = sy
    return gx, gy


def terrain_gradients(z: np.ndarray, crs: str, transform: Affine) -> tuple[np.ndarray, np.ndarray]:
    dx, dy = cell_sizes_m(crs, transform, z.shape[0])
    return horn_gradients(z, dx, dy)


def slope_from_gradients(gx: np.ndarray, gy: np.ndarray) -> np.ndarray:
    return np.rad2deg(np.arctan(np.hypot(gx.astype(np.float64), gy))).astype(np.float32)


def slope_degrees(z: np.ndarray, crs: str, transform: Affine) -> np.ndarray:
    """Slope in degrees (0-90), float32, NaN where undefined."""
    return slope_from_gradients(*terrain_gradients(z, crs, transform))


def slope_percent(slope_deg: np.ndarray) -> np.ndarray:
    """Percent slope = 100 * tan(slope); NaN preserved."""
    return (100.0 * np.tan(np.deg2rad(slope_deg.astype(np.float64)))).astype(np.float32)
