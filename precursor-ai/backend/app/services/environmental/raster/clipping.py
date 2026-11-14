"""Clip rasters to an AOI polygon (EPSG:4326 in, transformed to the raster CRS explicitly with pyproj).

Pixels whose centre lies outside the polygon become NaN (float32). Coverage % is the fraction of the AOI area that lies
inside the source footprint, measured in the raster CRS plane (for geographic rasters this is a ratio of square
degrees, an approximation). NotAvailable = AOI does not intersect the source; EnvError = invalid input geometry.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import shapely
from affine import Affine
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.transform import array_bounds
from shapely.geometry import MultiPolygon, Polygon, box


from app.services.environmental.raster.io import read_float, write_geotiff
from app.services.environmental.types import EnvError, NotAvailable


@dataclass
class ClipResult:
    array: np.ndarray
    transform: Affine
    crs: str
    coverage_percent: float  # AOI area inside the source footprint
    valid_in_aoi_percent: float  # finite pixels among pixels inside the AOI
    pixels_in_aoi: int
    tags: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def validate_aoi(aoi) -> Polygon | MultiPolygon:
    if not isinstance(aoi, (Polygon, MultiPolygon)):
        raise EnvError("AOI must be a shapely Polygon or MultiPolygon in EPSG:4326")
    if aoi.is_empty or not aoi.is_valid:
        raise EnvError("AOI geometry is empty or invalid")
    minx, miny, maxx, maxy = aoi.bounds
    if not all(math.isfinite(v) for v in (minx, miny, maxx, maxy)) or minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
        raise EnvError("AOI coordinates must be finite lon/lat within [-180,180] x [-90,90]")
    return aoi


def aoi_to_crs(aoi, crs: str):
    """EPSG:4326 -> raster CRS, with edges densified so curved edges stay faithful."""
    g = validate_aoi(aoi)
    minx, miny, maxx, maxy = g.bounds
    g = shapely.segmentize(g, max(maxx - minx, maxy - miny, 1e-6) / 50.0)
    t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    out = shapely.transform(g, lambda c: np.column_stack(t.transform(c[:, 0], c[:, 1])))
    if out.is_empty or not all(math.isfinite(v) for v in out.bounds):
        raise EnvError("AOI cannot be transformed into the raster CRS (outside its domain)")
    return out


def clip_array(arr: np.ndarray, transform: Affine, crs: str, aoi) -> ClipResult:
    if transform.b != 0 or transform.d != 0 or transform.a <= 0 or transform.e >= 0:
        raise EnvError("clip_array requires a north-up, non-rotated grid")
    g = aoi_to_crs(aoi, crs)
    if g.area <= 0:
        raise EnvError("AOI has zero area")
    h, w = arr.shape
    inter = g.intersection(box(*array_bounds(h, w, transform)))
    if inter.is_empty or inter.area == 0:
        raise NotAvailable("AOI does not intersect the raster footprint")
    coverage = 100.0 * inter.area / g.area
    inv = ~transform
    (c_a, r_a), (c_b, r_b) = inv @ (inter.bounds[0], inter.bounds[3]), inv @ (inter.bounds[2], inter.bounds[1])
    c0, c1 = max(0, math.floor(c_a + 1e-9)), min(w, math.ceil(c_b - 1e-9))
    r0, r1 = max(0, math.floor(r_a + 1e-9)), min(h, math.ceil(r_b - 1e-9))
    if c1 <= c0 or r1 <= r0:
        raise NotAvailable("AOI is smaller than one pixel of the raster")
    sub = arr[r0:r1, c0:c1]
    t_sub = transform @ Affine.translation(c0, r0)
    inside = geometry_mask([g], out_shape=sub.shape, transform=t_sub, invert=True)
    if not inside.any():
        raise NotAvailable("AOI contains no pixel centres of the raster")
    out = np.where(inside, sub, np.float32(np.nan)).astype(np.float32)
    n_in = int(inside.sum())
    valid_pct = 100.0 * int(np.isfinite(out).sum()) / n_in
    warns = []
    if coverage < 99.999:
        warns.append(f"source covers only {coverage:.2f}% of the AOI; the remainder is missing, not filled")
    if valid_pct < 100.0:
        warns.append(f"{100.0 - valid_pct:.2f}% of pixels inside the AOI are nodata (NaN)")
    return ClipResult(out, t_sub, crs, round(coverage, 4), round(valid_pct, 4), n_in, warnings=warns)


def clip_raster(path: str | Path, aoi, dst: str | Path | None = None, extra_tags: dict[str, str] | None = None) -> ClipResult:
    arr, meta = read_float(path)
    if meta.crs is None:
        raise EnvError(f"{meta.source_name}: CRS missing; refusing to guess one for clipping")
    res = clip_array(arr, Affine(*meta.transform), meta.crs, aoi)
    res.tags = {**meta.tags, "source": meta.source_name, "aoi_coverage_percent": str(res.coverage_percent), **(extra_tags or {})}
    if meta.units:
        res.tags["units"] = meta.units
    if dst is not None:
        write_geotiff(dst, res.array, res.transform, res.crs, res.tags)
    return res
