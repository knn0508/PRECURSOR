"""Reproject/resample rasters onto a target grid with a resampling method chosen by what the layer MEANS.

* continuous (elevation, slope, soil, rainfall, InSAR): bilinear
* categorical (LAND_COVER): nearest only; class ids are never interpolated, so no new ids can appear
* circular (ASPECT): resampled as sin/cos components and recombined with atan2; raw 0-360 degrees are never bilinear-ed

Resampling does NOT add information: upsampling only interpolates, it cannot recover detail finer than the native
resolution. Native and processing resolution are both reported. NaN is nodata on input and output.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from affine import Affine
from rasterio.crs import CRS
from rasterio.warp import Resampling, reproject

from app.services.environmental.raster.io import RasterMeta, read_float, write_geotiff
from app.services.environmental.types import CATEGORICAL_KINDS, CIRCULAR_KINDS, EnvError, LayerKind  # noqa: F401

_MIN_RESULTANT = 1e-3  # |mean unit vector| below this: directions cancelled, mean aspect undefined -> NaN


@dataclass(frozen=True)
class TargetGrid:
    crs: str
    transform: Affine
    width: int
    height: int

    def resolution(self) -> dict:
        unit = "degree" if CRS.from_string(self.crs).is_geographic else "crs_linear_unit"
        return {"x": abs(self.transform.a), "y": abs(self.transform.e), "unit": unit}


def grid_from_meta(meta: RasterMeta) -> TargetGrid:
    if meta.crs is None:
        raise EnvError("cannot build a grid from a raster without a CRS")
    return TargetGrid(meta.crs, Affine(*meta.transform), meta.width, meta.height)


@dataclass
class AlignResult:
    array: np.ndarray
    grid: TargetGrid
    native_resolution: dict
    processing_resolution: dict
    warnings: list[str] = field(default_factory=list)


def resampling_for(kind: LayerKind) -> Resampling:
    """Nearest for categorical kinds, bilinear otherwise. For ASPECT the returned bilinear is ONLY valid on the sin/cos
    components; `align_array` does that automatically. Never apply it to raw aspect degrees."""
    return Resampling.nearest if kind in CATEGORICAL_KINDS else Resampling.bilinear


def _warp(arr: np.ndarray, src_transform: Affine, src_crs: str, grid: TargetGrid, method: Resampling) -> np.ndarray:
    dst = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
    reproject(arr.astype(np.float32, copy=False), dst, src_transform=src_transform, src_crs=src_crs,
              dst_transform=grid.transform, dst_crs=grid.crs, resampling=method, src_nodata=np.nan, dst_nodata=np.nan)
    return dst


def _circular_warp(aspect: np.ndarray, src_transform: Affine, src_crs: str, grid: TargetGrid) -> tuple[np.ndarray, int]:
    rad = np.deg2rad(aspect.astype(np.float64))
    s = _warp(np.sin(rad), src_transform, src_crs, grid, Resampling.bilinear).astype(np.float64)
    c = _warp(np.cos(rad), src_transform, src_crs, grid, Resampling.bilinear).astype(np.float64)
    r = np.hypot(s, c)
    out = np.mod(np.rad2deg(np.arctan2(s, c)), 360.0).astype(np.float32)
    out[np.mod(out, 360.0) != out] = 0.0  # float32 rounding of 359.99999 -> 360
    undefined = np.isfinite(r) & (r < _MIN_RESULTANT)
    out[~np.isfinite(r) | undefined] = np.nan
    return out, int(undefined.sum())


def align_array(arr: np.ndarray, src_transform: Affine, src_crs: str, native_resolution: dict, grid: TargetGrid,
                kind: LayerKind) -> AlignResult:
    if not src_crs:
        raise EnvError("source CRS missing; refusing to guess one for resampling")
    warns = ["resampling does not add information; processing resolution cannot reveal detail finer than native"]
    if kind in CIRCULAR_KINDS:
        out, undefined = _circular_warp(arr, src_transform, src_crs, grid)
        warns.append("aspect resampled via sin/cos components (circular-aware)")
        if undefined:
            warns.append(f"{undefined} pixels set to NaN where averaged directions cancel (undefined mean aspect)")
    else:
        out = _warp(arr, src_transform, src_crs, grid, resampling_for(kind))
        if kind in CATEGORICAL_KINDS:
            warns.append("categorical layer resampled with nearest neighbour; class ids preserved")
    proc = grid.resolution()
    if CRS.from_string(src_crs) == CRS.from_string(grid.crs) and proc["x"] > 2 * native_resolution["x"]:
        warns.append("target is >2x coarser than native; bilinear subsampling aliases (no area averaging performed)")
    return AlignResult(out, grid, native_resolution, proc, warns)


def align_to_grid(src_path: str | Path, grid: TargetGrid, kind: LayerKind, dst_path: str | Path | None = None) -> AlignResult:
    arr, meta = read_float(src_path)
    if meta.crs is None:
        raise EnvError(f"{meta.source_name}: CRS missing; refusing to guess one for resampling")
    res = align_array(arr, Affine(*meta.transform), meta.crs, meta.resolution(), grid, kind)
    if dst_path is not None:
        tags = {**meta.tags, "source": meta.source_name, "resampling": "nearest" if kind in CATEGORICAL_KINDS else
                ("circular_sincos" if kind in CIRCULAR_KINDS else "bilinear")}
        if meta.units:
            tags["units"] = meta.units
        write_geotiff(dst_path, res.array, grid.transform, grid.crs, tags)
    return res
