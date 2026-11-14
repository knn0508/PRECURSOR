"""Mosaic tiles (GeoTIFF / .hgt / .zip) onto one canvas.

Deterministic rules (all reported in `warnings`):
* tiles are processed in sorted file-name order; the FIRST tile's valid value wins, later tiles only fill NaN cells
* where two tiles both have a valid value the values are compared; disagreement beyond `overlap_tol` is warned
* cells no tile covers (missing tile / gap) stay NaN and are reported, never filled
* mixed CRS or resolution is rejected with EnvError unless the caller passes an explicit `target_grid`, in which case every
  tile is resampled onto it first (shortcut: each aligned tile is grid-sized in memory; keep target grids tile-scale)
* mixed or undeclared units / vertical datum tags are warned about; datums are never assumed identical
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from affine import Affine
from rasterio.crs import CRS

from app.services.environmental.raster.alignment import TargetGrid, align_array
from app.services.environmental.raster.io import RasterMeta, read_float, write_geotiff
from app.services.environmental.types import SYNTHETIC_TAG, EnvError, LayerKind

_DATUM_TAGS = ("vertical_datum", "vertical_reference")


@dataclass
class MosaicResult:
    array: np.ndarray
    transform: Affine
    crs: str
    tags: dict[str, str]
    warnings: list[str]
    tiles_used: list[str]
    valid_percent_of_extent: float
    gap_percent_of_extent: float  # canvas cells covered by no tile
    overlap_pixels: int  # cells covered by more than one tile footprint
    overlap_max_abs_diff: float | None
    native_resolution: dict = field(default_factory=dict)
    meta: list[RasterMeta] = field(default_factory=list)


def _check_same_grid(metas: list[RasterMeta]) -> None:
    ref = metas[0]
    for m in metas:
        if m.crs is None:
            raise EnvError(f"{m.source_name}: CRS missing; refusing to guess one")
    if any(CRS.from_string(m.crs) != CRS.from_string(ref.crs) for m in metas):
        raise EnvError("mixed CRS among tiles; pass an explicit target_grid to reproject, or align tiles first")
    for m in metas:
        if not (np.isclose(m.res_x, ref.res_x, rtol=1e-9) and np.isclose(m.res_y, ref.res_y, rtol=1e-9)):
            raise EnvError("mixed resolution among tiles; pass an explicit target_grid to resample")
        if m.transform[1] != 0 or m.transform[3] != 0 or m.transform[4] >= 0:
            raise EnvError(f"{m.source_name}: only north-up, non-rotated tiles are supported")


def _unit_datum_warnings(metas: list[RasterMeta]) -> tuple[list[str], dict[str, str]]:
    warns, tags = [], {}
    units = {m.units for m in metas}
    if None in units:
        warns.append("units not declared in at least one tile; none assumed")
    known = {u for u in units if u}
    if len(known) > 1:
        warns.append(f"mixed units across tiles: {sorted(known)}")
    elif len(known) == 1 and None not in units:
        tags["units"] = next(iter(known))
    datums = {m.tags.get(k) for m in metas for k in _DATUM_TAGS if m.tags.get(k)}
    if not datums:
        warns.append("vertical datum not declared in any tile; tiles are NOT assumed to share a datum")
    elif len(datums) > 1:
        warns.append(f"mixed vertical datum declarations across tiles: {sorted(datums)}")
    elif any(not any(m.tags.get(k) for k in _DATUM_TAGS) for m in metas):
        warns.append("vertical datum declared for some tiles only")
    else:
        tags["vertical_datum"] = next(iter(datums))
    return warns, tags


def mosaic_rasters(paths: list[str | Path], *, target_grid: TargetGrid | None = None,
                   kind: LayerKind = LayerKind.ELEVATION, overlap_tol: float = 1e-3,
                   dst: str | Path | None = None) -> MosaicResult:
    if not paths:
        raise EnvError("mosaic needs at least one tile")
    loaded = sorted(((Path(p).name, *read_float(p)) for p in paths), key=lambda t: t[0])
    names, arrs, metas = [t[0] for t in loaded], [t[1] for t in loaded], [t[2] for t in loaded]
    warns: list[str] = []
    if target_grid is not None:
        for m in metas:
            if m.crs is None:
                raise EnvError(f"{m.source_name}: CRS missing; refusing to guess one")
        arrs = [align_array(a, Affine(*m.transform), m.crs, m.resolution(), target_grid, kind).array
                for a, m in zip(arrs, metas)]
        origins = [(0, 0)] * len(arrs)
        transform, crs, (hh, ww) = target_grid.transform, target_grid.crs, (target_grid.height, target_grid.width)
        warns.append("tiles resampled onto the explicit target grid before mosaicking (no information added)")
    else:
        _check_same_grid(metas)
        rx, ry, crs = metas[0].res_x, metas[0].res_y, metas[0].crs
        west = min(m.bounds[0] for m in metas)
        north = max(m.bounds[3] for m in metas)
        east = max(m.bounds[2] for m in metas)
        south = min(m.bounds[1] for m in metas)
        ww, hh = round((east - west) / rx), round((north - south) / ry)
        origins = []
        for m in metas:
            c, r = (m.bounds[0] - west) / rx, (north - m.bounds[3]) / ry
            if abs(c - round(c)) > 1e-3 or abs(r - round(r)) > 1e-3:
                raise EnvError(f"{m.source_name}: tile grid is not pixel-aligned with the others; use target_grid")
            origins.append((round(r), round(c)))
        transform = Affine(rx, 0, west, 0, -ry, north)
    canvas = np.full((hh, ww), np.nan, dtype=np.float32)
    count = np.zeros((hh, ww), dtype=np.int16)
    max_diff = None
    for a, (r0, c0) in zip(arrs, origins):
        h, w = a.shape
        view, cview = canvas[r0:r0 + h, c0:c0 + w], count[r0:r0 + h, c0:c0 + w]
        both = np.isfinite(a) & np.isfinite(view)
        if both.any():
            d = float(np.abs(view[both].astype(np.float64) - a[both]).max())
            max_diff = d if max_diff is None else max(max_diff, d)
        fill = np.isfinite(a) & ~np.isfinite(view)
        view[fill] = a[fill]
        cview += 1
    overlap = int((count > 1).sum())
    if overlap:
        warns.append(f"{overlap} cells lie in more than one tile; rule: first tile in sorted file-name order wins where valid")
    if max_diff is not None and max_diff > overlap_tol:
        warns.append(f"overlapping tiles DISAGREE: max |difference| {max_diff:g} exceeds tolerance {overlap_tol:g}; "
                     "tile order decided the value")
    gap = 100.0 * float((count == 0).sum()) / count.size
    if gap > 0:
        warns.append(f"{gap:.2f}% of the mosaic extent is covered by no tile (missing tile or gap); left NaN, not filled")
    valid = 100.0 * int(np.isfinite(canvas).sum()) / canvas.size
    if valid < 100.0 - gap:
        warns.append(f"{100.0 - gap - valid:.2f}% of tile-covered cells are nodata (NaN)")
    w2, tags = _unit_datum_warnings(metas)
    warns += w2
    tags["source"] = ",".join(names)
    if any(m.is_synthetic for m in metas):
        tags[SYNTHETIC_TAG] = "1"
        if not all(m.is_synthetic for m in metas):
            warns.append("mix of synthetic and non-synthetic tiles; output marked synthetic")
    if dst is not None:
        write_geotiff(dst, canvas, transform, crs, tags)
    return MosaicResult(canvas, transform, crs, tags, warns, names, round(valid, 4), round(gap, 4), overlap, max_diff,
                        metas[0].resolution(), metas)
