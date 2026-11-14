"""Raster windowing and normalisation. Never resamples; CRS and transform are carried, never guessed.

`tiled_apply` runs a pure array->array function on padded tiles and stitches the unpadded cores, which bounds the
temporaries of big rasters. For a function whose reach is <= `halo` pixels the result equals the whole-array result
(tested). Normalisation records its parameters so it can be inverted and audited.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from affine import Affine
from rasterio.windows import Window

from app.services.environmental.raster.io import gdal_path
from app.services.features_cv.types import FeatureError


@dataclass(frozen=True)
class Tile:
    core: tuple[int, int, int, int]  # r0, r1, c0, c1 (the part this tile OWNS in the output)
    read: tuple[int, int, int, int]  # core grown by the halo and clipped to the raster


def iter_tiles(height: int, width: int, tile: int, halo: int) -> Iterator[Tile]:
    if height < 1 or width < 1:
        raise FeatureError("raster has no pixels")
    if tile < 1 or halo < 0:
        raise FeatureError("tile must be >= 1 and halo >= 0")
    for r0 in range(0, height, tile):
        for c0 in range(0, width, tile):
            r1, c1 = min(r0 + tile, height), min(c0 + tile, width)
            yield Tile((r0, r1, c0, c1), (max(0, r0 - halo), min(height, r1 + halo), max(0, c0 - halo), min(width, c1 + halo)))


def tiled_apply(arr: np.ndarray, func: Callable[[np.ndarray, int], np.ndarray], *, tile: int = 512, halo: int = 0) -> np.ndarray:
    """func(block, first_row) must keep the block shape (first_row lets it slice per-row cell sizes). Output is float32
    NaN-initialised, so an unfilled pixel is missing, never zero."""
    if arr.ndim != 2:
        raise FeatureError("expected a 2-D array")
    out = np.full(arr.shape, np.nan, dtype=np.float32)
    for t in iter_tiles(arr.shape[0], arr.shape[1], tile, halo):
        R0, R1, C0, C1 = t.read
        r0, r1, c0, c1 = t.core
        res = func(arr[R0:R1, C0:C1], R0)
        if res.shape != (R1 - R0, C1 - C0):
            raise FeatureError("tiled function changed the array shape")
        out[r0:r1, c0:c1] = res[r0 - R0:r1 - R0, c0 - C0:c1 - C0]
    return out


def read_window(path: str | Path, window: Window, band: int = 1) -> tuple[np.ndarray, Affine]:
    """Windowed float32 read with nodata -> NaN; also returns the window's affine so georeferencing is preserved."""
    with rasterio.open(gdal_path(path)) as ds:
        arr = ds.read(band, window=window).astype(np.float32)
        nd = ds.nodata
        tf = ds.window_transform(window)
    if nd is not None and not np.isnan(nd):
        arr[arr == np.float32(nd)] = np.nan
    return arr, tf


def assert_same_grid(a: dict[str, Any], b: dict[str, Any]) -> None:
    """Both dicts hold crs, transform (6 numbers), width, height. No silent resampling: a mismatch is an error."""
    for k in ("crs", "width", "height"):
        if a.get(k) != b.get(k):
            raise FeatureError(f"grid mismatch on {k}: {a.get(k)!r} vs {b.get(k)!r}; inputs must share one grid (no silent resampling)")
    ta, tb = a.get("transform"), b.get("transform")
    if ta is None or tb is None or not np.allclose(ta, tb, rtol=0, atol=1e-9):
        raise FeatureError("grid mismatch on transform; inputs must share one grid (no silent resampling)")


@dataclass
class Normalisation:
    method: str  # zscore | minmax
    params: dict[str, float]
    n_valid: int

    def apply(self, arr: np.ndarray) -> np.ndarray:
        a = arr.astype(np.float64)
        if self.method == "zscore":
            out = (a - self.params["mean"]) / self.params["std"]
        else:
            out = (a - self.params["min"]) / (self.params["max"] - self.params["min"])
        return out.astype(np.float32)  # NaN stays NaN

    def invert(self, arr: np.ndarray) -> np.ndarray:
        a = arr.astype(np.float64)
        if self.method == "zscore":
            out = a * self.params["std"] + self.params["mean"]
        else:
            out = a * (self.params["max"] - self.params["min"]) + self.params["min"]
        return out.astype(np.float32)

    def to_dict(self) -> dict[str, Any]:
        return {"method": self.method, "params": dict(self.params), "n_valid": self.n_valid}


def fit_normalisation(arr: np.ndarray, method: str = "zscore") -> Normalisation:
    """Parameters come from VALID pixels only (NaN/inf ignored). A constant or empty raster cannot be normalised: error."""
    if method not in ("zscore", "minmax"):
        raise FeatureError(f"unknown normalisation {method!r}")
    v = arr[np.isfinite(arr)].astype(np.float64)
    if v.size == 0:
        raise FeatureError("no valid pixels to fit a normalisation")
    if method == "zscore":
        std = float(v.std())
        if std == 0.0:
            raise FeatureError("constant raster: z-score undefined")
        return Normalisation("zscore", {"mean": float(v.mean()), "std": std}, int(v.size))
    lo, hi = float(v.min()), float(v.max())
    if lo == hi:
        raise FeatureError("constant raster: min-max undefined")
    return Normalisation("minmax", {"min": lo, "max": hi}, int(v.size))
