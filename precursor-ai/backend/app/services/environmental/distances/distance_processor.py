"""User-provided GeoJSON rivers/faults/roads -> Euclidean distance (METRES) from each pixel CENTRE to the nearest feature.

Geometry is transformed from its declared CRS into the metric grid CRS with pyproj BEFORE any distance is computed; degrees are
never used as metres. Every feature in the input is used (also those outside the AOI), so the nearest feature just beyond the
AOI edge is found. Memory: pixel centres are processed in blocks of at most BLOCK_CELLS points; grids above `max_cells`
(default 4,000,000) are refused rather than left to hang. Polygons: distance to the filled area (0 inside).
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401  (must precede geo libraries)

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely import STRtree

from app.services.environmental.external_inputs import (
    aoi_mask, aoi_quality, input_hash, origin_of, read_geojson, require_metric_grid, to_grid_crs,
)
from app.services.environmental.raster.alignment import TargetGrid
from app.services.environmental.raster.io import write_geotiff
from app.services.environmental.types import (
    SYNTHETIC_TAG, EnvError, LayerKind, LayerQuality, LayerStatus, MeasurementKind, NotAvailable, Provenance,
)

KINDS = {"river": LayerKind.DISTANCE_RIVER, "fault": LayerKind.DISTANCE_FAULT, "road": LayerKind.DISTANCE_ROAD}
DEFAULT_MAX_CELLS = 4_000_000
BLOCK_CELLS = 200_000
_OK_TYPES = {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}


@dataclass
class DistanceResult:
    kind: str
    layer_kind: LayerKind
    path: Path
    quality: LayerQuality
    provenance: Provenance
    stats: dict[str, Any]
    status: LayerStatus
    warnings: list[str]
    input_hash: str


def distance_array(tree: STRtree, grid: TargetGrid) -> np.ndarray:
    """Metres from each pixel centre to the nearest tree geometry (grid CRS units), in row blocks."""
    t = grid.transform
    out = np.empty((grid.height, grid.width), dtype=np.float32)
    rows = max(1, BLOCK_CELLS // grid.width)
    cols = np.arange(grid.width) + 0.5
    for r0 in range(0, grid.height, rows):
        rr = np.arange(r0, min(r0 + rows, grid.height)) + 0.5
        cx, ry = np.meshgrid(cols, rr)
        x, y = t.a * cx + t.b * ry + t.c, t.d * cx + t.e * ry + t.f
        pts = shapely.points(x.ravel(), y.ravel())
        idx, d = tree.query_nearest(pts, return_distance=True, all_matches=False)
        flat = np.full(pts.shape[0], np.nan)
        flat[idx[0]] = d
        if np.isnan(flat).any():
            raise EnvError("nearest-feature search returned no result for some pixels")
        out[r0:r0 + rr.size] = flat.reshape(x.shape)
    return out


def process_distance(kind: str, files: list[Path], aoi: Any, grid: TargetGrid, out_dir: Path, *, max_cells: int = DEFAULT_MAX_CELLS) -> DistanceResult:
    if kind not in KINDS:
        raise EnvError(f"unknown distance kind {kind!r}; use one of {sorted(KINDS)}")
    require_metric_grid(grid)
    if grid.width * grid.height > max_cells:
        raise EnvError(f"grid has {grid.width * grid.height} cells, above max_cells={max_cells}; use a coarser grid or raise the limit")
    files = sorted(Path(f) for f in files)
    if not files:
        raise NotAvailable(f"no {kind} vector input covers the AOI")
    inside, warns = aoi_mask(aoi, grid)
    geoms: list = []
    skipped = 0
    synthetic = False
    for f in files:
        gs, _, crs, syn = read_geojson(f)
        synthetic |= syn
        n0 = skipped
        for g in gs:
            if g is None or g.is_empty or g.geom_type not in _OK_TYPES or not g.is_valid:
                skipped += 1
                continue
            g = to_grid_crs(g, crs, grid)
            if not np.isfinite(g.bounds).all():
                skipped += 1
                continue
            geoms.append(g)
        if skipped > n0:
            warns.append(f"{f.name}: {skipped - n0} feature(s) skipped (empty, invalid, unsupported type or untransformable)")
    if not geoms:
        raise NotAvailable(f"{kind} input holds no usable feature ({skipped} skipped)")
    d = distance_array(STRtree(geoms), grid)
    v = d[inside]
    tags = {"units": "metre", "source": ";".join(f.name for f in files), "crs": grid.crs,
            "method": "euclidean distance, pixel centre to nearest feature, metric grid CRS"}
    if synthetic:
        tags[SYNTHETIC_TAG] = "1"
    path = write_geotiff(Path(out_dir) / f"distance_{kind}.tif", d, grid.transform, grid.crs, tags)
    q = aoi_quality(d, inside, grid, None, passed=["features transformed to metric grid CRS", "no network/path distance"], failed=[], warnings=warns)
    stats = {"min_m": float(v.min()), "mean_m": float(v.mean()), "max_m": float(v.max()), "n_features": len(geoms),
             "n_skipped": skipped, "crs": grid.crs, "unit": "metre", "valid_percent": q.valid_percent}
    prov = Provenance(provider=f"USER_{kind.upper()}", dataset_name=f"user-provided {kind} GeoJSON", origin=origin_of(synthetic),
                      measurement_kind=MeasurementKind.DERIVED_MEASUREMENT, source_files=[f.name for f in files], units="metre",
                      method="Euclidean distance from pixel centres to nearest feature in the metric grid CRS (shapely STRtree.query_nearest)")
    status = LayerStatus.PARTIALLY_PROCESSED if skipped else LayerStatus.PROCESSED
    return DistanceResult(kind, KINDS[kind], path, q, prov, stats, status, warns,
                          input_hash(files, grid, aoi, {"kind": kind, "max_cells": max_cells}))
