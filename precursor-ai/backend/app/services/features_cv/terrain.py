"""Terrain-derived descriptive features: pure numpy/scipy/scikit-image functions, no I/O.

All functions take a float array (NaN = missing) and return float32 with NaN wherever the feature is undefined:
a NaN centre, a window with too many missing cells, or the raster border where the full neighbourhood does not exist
(missing is NEVER zero). Cell sizes are metres per row (reuse of Phase 4 `cell_sizes_m`), never degrees.

Definitions (docs/scientific/FEATURE_EXTRACTION.md):
* local relief      max - min of elevation in a size x size window (m)
* TRI               Riley et al. (1999): sqrt(sum over the 8 neighbours of (z_n - z_centre)^2) (m)
* curvature         Laplacian of the (optionally Gaussian-smoothed) surface, 1/m. Positive = concave-up (bowl/valley),
                    negative = convex-up (ridge). Profile/plan curvature are NOT provided: their sign conventions differ
                    between sources and an unverified convention would be a silent error.
* slope break       magnitude of the spatial gradient of slope (degrees per metre)
* lineament density fraction (0-1) of Canny edge pixels, from multi-azimuth hillshades, inside a window. The Canny
                    thresholds are edge-detector parameters on a 0-1 image; they are not hazard thresholds.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage as ndi
from skimage.feature import canny

from app.services.features_cv.types import FeatureError


def _odd(size: int, name: str = "window") -> int:
    if not isinstance(size, int) or isinstance(size, bool) or size < 3 or size % 2 == 0:
        raise FeatureError(f"{name} must be an odd integer >= 3 (got {size!r})")
    return size


def _frac(f: float) -> float:
    if not (isinstance(f, (int, float)) and 0 < f <= 1):
        raise FeatureError("min_valid_fraction must be in (0, 1]")
    return float(f)


def _f64(z: np.ndarray) -> np.ndarray:
    if z.ndim != 2:
        raise FeatureError("expected a 2-D array")
    return z.astype(np.float64)


def valid_counts(valid: np.ndarray, size: int) -> np.ndarray:
    """Number of valid cells in each size x size window; cells outside the raster count as missing."""
    return np.rint(ndi.uniform_filter(valid.astype(np.float64), size=size, mode="constant", cval=0.0) * size * size)


def local_relief(z: np.ndarray, size: int, min_valid_fraction: float = 0.5) -> np.ndarray:
    size, frac = _odd(size), _frac(min_valid_fraction)
    a = _f64(z)
    valid = np.isfinite(a)
    mx = ndi.maximum_filter(np.where(valid, a, -np.inf), size=size, mode="constant", cval=-np.inf)
    mn = ndi.minimum_filter(np.where(valid, a, np.inf), size=size, mode="constant", cval=np.inf)
    ok = valid & (valid_counts(valid, size) >= frac * size * size)
    out = np.where(ok, mx - mn, np.nan)
    return out.astype(np.float32)


def _neighbours(a: np.ndarray):
    """Views of the 8 neighbours and the centre for the interior cells: (z1..z9, row 0 = north)."""
    return (a[:-2, :-2], a[:-2, 1:-1], a[:-2, 2:], a[1:-1, :-2], a[1:-1, 1:-1], a[1:-1, 2:], a[2:, :-2], a[2:, 1:-1], a[2:, 2:])


def _interior(a: np.ndarray, inner: np.ndarray) -> np.ndarray:
    out = np.full(a.shape, np.nan, dtype=np.float64)
    if a.shape[0] >= 3 and a.shape[1] >= 3:
        out[1:-1, 1:-1] = inner
    return out


def terrain_ruggedness(z: np.ndarray) -> np.ndarray:
    """Riley TRI over the 3x3 neighbourhood; NaN if any of the 9 cells is missing."""
    a = _f64(z)
    if a.shape[0] < 3 or a.shape[1] < 3:
        return np.full(a.shape, np.nan, dtype=np.float32)
    z1, z2, z3, z4, z5, z6, z7, z8, z9 = _neighbours(a)
    with np.errstate(invalid="ignore"):
        tri = np.sqrt(sum((n - z5) ** 2 for n in (z1, z2, z3, z4, z6, z7, z8, z9)))
    return _interior(a, tri).astype(np.float32)


def gaussian_smooth(z: np.ndarray, sigma_px: float, min_weight: float = 0.5) -> np.ndarray:
    """NaN-aware Gaussian smoothing (normalised convolution). Data is never extended into missing cells; cells whose
    kernel weight is mostly missing (< min_weight) become NaN. sigma 0 returns the input unchanged."""
    a = _f64(z)
    if sigma_px < 0 or not math.isfinite(sigma_px):
        raise FeatureError("sigma must be a finite number >= 0")
    if sigma_px == 0:
        return a.astype(np.float32)
    valid = np.isfinite(a)
    num = ndi.gaussian_filter(np.where(valid, a, 0.0), sigma_px, mode="constant", cval=0.0)
    den = ndi.gaussian_filter(valid.astype(np.float64), sigma_px, mode="constant", cval=0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(valid & (den >= min_weight), num / den, np.nan)
    return out.astype(np.float32)


def curvature_laplacian(z: np.ndarray, dx_m: np.ndarray, dy_m: np.ndarray, sigma_px: float = 0.0) -> np.ndarray:
    """Laplacian curvature (1/m) of z, smoothed first when sigma_px > 0. dx_m/dy_m: metres per row, length = rows."""
    a = _f64(gaussian_smooth(z, sigma_px))
    if len(dx_m) != a.shape[0] or len(dy_m) != a.shape[0]:
        raise FeatureError("cell-size arrays must have one value per row")
    if a.shape[0] < 3 or a.shape[1] < 3:
        return np.full(a.shape, np.nan, dtype=np.float32)
    _, z2, _, z4, z5, z6, _, z8, _ = _neighbours(a)
    dx, dy = np.asarray(dx_m, dtype=np.float64)[1:-1, None], np.asarray(dy_m, dtype=np.float64)[1:-1, None]
    with np.errstate(invalid="ignore"):
        lap = (z4 + z6 - 2 * z5) / dx ** 2 + (z2 + z8 - 2 * z5) / dy ** 2
    return _interior(a, lap).astype(np.float32)


def slope_break(slope_deg: np.ndarray, dx_m: np.ndarray, dy_m: np.ndarray) -> np.ndarray:
    """|grad(slope)| in degrees per metre (central differences); NaN unless all four neighbours are valid."""
    s = _f64(slope_deg)
    if len(dx_m) != s.shape[0] or len(dy_m) != s.shape[0]:
        raise FeatureError("cell-size arrays must have one value per row")
    if s.shape[0] < 3 or s.shape[1] < 3:
        return np.full(s.shape, np.nan, dtype=np.float32)
    dx, dy = np.asarray(dx_m, dtype=np.float64)[1:-1, None], np.asarray(dy_m, dtype=np.float64)[1:-1, None]
    with np.errstate(invalid="ignore"):
        gx = (s[1:-1, 2:] - s[1:-1, :-2]) / (2 * dx)
        gy = (s[:-2, 1:-1] - s[2:, 1:-1]) / (2 * dy)  # north-positive
        mag = np.hypot(gx, gy)
    centre = np.isfinite(s[1:-1, 1:-1])
    return _interior(s, np.where(centre, mag, np.nan)).astype(np.float32)


def hillshade(gx: np.ndarray, gy: np.ndarray, azimuth_deg: float, altitude_deg: float = 45.0) -> np.ndarray:
    """Lambertian shade in [0, 1] from east-/north-positive gradients; azimuth clockwise from north. NaN stays NaN."""
    if not (0 <= altitude_deg <= 90):
        raise FeatureError("sun altitude must be 0-90 degrees")
    az, alt = math.radians(azimuth_deg), math.radians(altitude_deg)
    lx, ly, lz = math.sin(az) * math.cos(alt), math.cos(az) * math.cos(alt), math.sin(alt)
    gx64, gy64 = gx.astype(np.float64), gy.astype(np.float64)
    norm = np.sqrt(gx64 ** 2 + gy64 ** 2 + 1.0)
    shade = (-gx64 * lx - gy64 * ly + lz) / norm
    return np.clip(shade, 0.0, 1.0).astype(np.float32)


def lineament_density(gx: np.ndarray, gy: np.ndarray, size: int, *, azimuths: tuple[float, ...] = (0.0, 45.0, 90.0, 135.0, 225.0, 315.0),
                      altitude_deg: float = 45.0, sigma: float = 1.0, low: float = 0.02, high: float = 0.06,
                      min_valid_fraction: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """(density 0-1 per window, union edge map as float32 0/1/NaN). Edges within one cell of missing data are dropped
    because the NaN fill (0) would create artificial edges."""
    size, frac = _odd(size), _frac(min_valid_fraction)
    if gx.shape != gy.shape:
        raise FeatureError("gradient arrays must share a shape")
    if not azimuths:
        raise FeatureError("at least one azimuth is required")
    if not (0 <= low <= high):
        raise FeatureError("Canny thresholds need 0 <= low <= high")
    valid = np.isfinite(gx) & np.isfinite(gy)
    safe = ndi.binary_erosion(valid, structure=np.ones((3, 3), bool), border_value=0)
    edges = np.zeros(valid.shape, dtype=bool)
    for az in azimuths:
        hs = np.where(valid, hillshade(np.where(valid, gx, 0.0), np.where(valid, gy, 0.0), az, altitude_deg), 0.0)
        edges |= canny(hs.astype(np.float64), sigma=sigma, low_threshold=low, high_threshold=high)
    edges &= safe
    cnt = valid_counts(valid, size)
    s = ndi.uniform_filter((edges & valid).astype(np.float64), size=size, mode="constant", cval=0.0) * size * size
    with np.errstate(invalid="ignore", divide="ignore"):
        dens = np.where(valid & (cnt >= frac * size * size), s / cnt, np.nan)
    return dens.astype(np.float32), np.where(valid, edges.astype(np.float32), np.nan)
