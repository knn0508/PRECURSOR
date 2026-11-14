"""GLCM texture on a block grid. Pure functions, no I/O.

A per-pixel GLCM over a big raster is prohibitively slow, so texture is computed per `window` x `window` block and the
result lives on a COARSER block grid (cell = stride x reference cell) with its own transform. That is declared, never a
silent resampling. A block with ANY missing pixel is NaN (a GLCM of partial data would mix unequal samples). The raster
is quantised to `levels` grey levels between fixed bounds that are RETURNED so the run can be reproduced; values outside
the bounds are clipped and counted.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from skimage.feature import graycomatrix, graycoprops

from app.services.features_cv.types import FeatureError

PROPS = ("contrast", "dissimilarity", "homogeneity", "energy", "correlation", "ASM")
_ANGLES = (0.0, math.pi / 4, math.pi / 2, 3 * math.pi / 4)


@dataclass
class TextureResult:
    layers: dict[str, np.ndarray]  # property -> block-grid array (float32, NaN = undefined)
    stride: int
    vmin: float
    vmax: float
    levels: int
    n_clipped: int
    n_blocks: int
    n_blocks_valid: int


def quantise(a: np.ndarray, vmin: float, vmax: float, levels: int) -> tuple[np.ndarray, int]:
    """float -> uint8 levels 0..levels-1 over [vmin, vmax]; NaN -> 0 (callers mask NaN blocks). Returns (q, n_clipped)."""
    if not (2 <= levels <= 256):
        raise FeatureError("levels must be 2-256")
    if not (math.isfinite(vmin) and math.isfinite(vmax) and vmax > vmin):
        raise FeatureError("quantisation bounds need finite vmin < vmax")
    valid = np.isfinite(a)
    clipped = int(np.count_nonzero(valid & ((a < vmin) | (a > vmax))))
    t = np.clip((np.where(valid, a, vmin) - vmin) / (vmax - vmin), 0.0, 1.0)
    return np.minimum((t * levels).astype(np.int64), levels - 1).astype(np.uint8), clipped


def glcm_blocks(a: np.ndarray, window: int, *, levels: int = 16, vmin: float | None = None, vmax: float | None = None,
                distance: int = 1) -> TextureResult:
    """Texture statistics per non-overlapping window x window block, averaged over 4 directions (symmetric GLCM)."""
    if a.ndim != 2:
        raise FeatureError("expected a 2-D array")
    if not isinstance(window, int) or window < 3:
        raise FeatureError("window must be an integer >= 3")
    if distance < 1 or distance >= window:
        raise FeatureError("distance must be >= 1 and smaller than the window")
    a = a.astype(np.float64)
    finite = a[np.isfinite(a)]
    if finite.size == 0:
        raise FeatureError("no valid pixels")
    lo = float(finite.min()) if vmin is None else float(vmin)
    hi = float(finite.max()) if vmax is None else float(vmax)
    if hi <= lo:
        raise FeatureError("constant raster: texture is undefined")
    q, n_clip = quantise(a, lo, hi, levels)
    nbr, nbc = a.shape[0] // window, a.shape[1] // window  # partial edge blocks are dropped, not padded
    if nbr == 0 or nbc == 0:
        raise FeatureError(f"raster {a.shape[0]}x{a.shape[1]} is smaller than one {window}x{window} texture window")
    out = {p: np.full((nbr, nbc), np.nan, dtype=np.float32) for p in PROPS}
    n_valid = 0
    for i in range(nbr):
        for j in range(nbc):
            sl = (slice(i * window, (i + 1) * window), slice(j * window, (j + 1) * window))
            blk = a[sl]
            if not np.isfinite(blk).all():
                continue
            n_valid += 1
            glcm = graycomatrix(q[sl], distances=[distance], angles=list(_ANGLES), levels=levels, symmetric=True, normed=True)
            const = float(blk.max() - blk.min()) == 0.0
            for p in PROPS:
                if p == "correlation" and const:
                    continue  # skimage returns 1.0 for a constant window; that is a convention, not a measurement
                out[p][i, j] = float(graycoprops(glcm, p).mean())
    return TextureResult(out, window, lo, hi, levels, n_clip, nbr * nbc, n_valid)
