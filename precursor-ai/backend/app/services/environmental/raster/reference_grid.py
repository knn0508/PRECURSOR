"""Common metric reference grid: choose a projected CRS from the AOI, build a deterministic metre grid, align layers to it.

Rules (see docs/scientific/REFERENCE_GRID.md): the CRS is derived from the AOI centroid (UTM zone, polar stereographic
beyond 84 degrees), never hard-coded; the grid is in METRES (degrees are never used as metres); the origin is snapped to
multiples of the resolution so identical inputs give identical grids; categorical layers use nearest only and keep their
integer dtype; missing is NaN/declared nodata, never zero. Resampling does not add information.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from affine import Affine
from pyproj import CRS, Geod, Transformer
from rasterio.features import geometry_mask
from shapely.geometry import box
from shapely.ops import transform as shp_transform

from app.services.environmental.raster.alignment import TargetGrid, align_to_grid
from app.services.environmental.raster.io import inspect_raster, write_geotiff
from app.services.environmental.raster.quality import layer_quality
from app.services.environmental.types import CATEGORICAL_KINDS, CIRCULAR_KINDS, EnvError, LayerKind, LayerQuality, NotAvailable

__all__ = ["CrsChoice", "ReferenceGrid", "AlignedLayer", "choose_projected_crs", "build_reference_grid", "align_layer_to_reference"]

POLAR_LAT = 84.0
_SVALBARD = ((0, 9, 31), (9, 21, 33), (21, 33, 35), (33, 42, 37))  # lon ranges (deg E) for lat 72-84 N


@dataclass
class CrsChoice:
    epsg: int
    name: str
    kind: str  # 'utm' | 'polar'
    zone: int | None
    hemisphere: str  # 'north' | 'south'
    warnings: list[str] = field(default_factory=list)


@dataclass
class ReferenceGrid:
    grid: TargetGrid
    epsg: int | None
    resolution_m: float
    bounds: tuple[float, float, float, float]  # left, bottom, right, top in the grid CRS (metres)
    chosen_by: str  # 'auto' | 'user'
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        g = self.grid
        return {"crs": g.crs, "epsg": self.epsg, "resolution": {"x": self.resolution_m, "y": self.resolution_m, "unit": "metre"},
                "width": g.width, "height": g.height, "bounds": list(self.bounds), "transform": list(tuple(g.transform)[:6]),
                "chosen_by": self.chosen_by, "warnings": list(self.warnings)}


@dataclass
class AlignedLayer:
    path: Path
    quality: LayerQuality
    resampling: str


def _bounds_and_centroid(aoi: Any) -> tuple[tuple[float, float, float, float], tuple[float, float]]:
    if hasattr(aoi, "bounds") and hasattr(aoi, "centroid"):
        if aoi.is_empty:
            raise EnvError("AOI is empty")
        if hasattr(aoi, "is_valid") and not aoi.is_valid:
            raise EnvError("AOI geometry is invalid")
        b, c = tuple(float(v) for v in aoi.bounds), (aoi.centroid.x, aoi.centroid.y)
    else:
        try:
            b = tuple(float(v) for v in aoi)
        except (TypeError, ValueError):
            raise EnvError("AOI must be a shapely geometry or (west, south, east, north)") from None
        if len(b) != 4:
            raise EnvError("AOI must be a shapely geometry or (west, south, east, north)")
        c = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    if not all(math.isfinite(v) for v in b):
        raise EnvError("AOI has non-finite coordinates")
    w, s, e, n = b
    if w > e:
        raise EnvError("AOI crosses the antimeridian (west > east): not supported; split the AOI at 180 degrees")
    if not (-180 <= w and e <= 180 and -90 <= s <= n <= 90):
        raise EnvError(f"AOI out of range: {b}")
    return b, c


def _utm_zone(lon: float, lat: float) -> int:
    z = min(int(math.floor((lon + 180.0) / 6.0)) + 1, 60)
    if 56 <= lat < 64 and 3 <= lon < 12:
        return 32  # Norway exception
    if 72 <= lat < 84:  # Svalbard exceptions (zones 32, 34, 36 are not used)
        for lo, hi, zz in _SVALBARD:
            if lo <= lon < hi:
                return zz
    return z


def choose_projected_crs(aoi_wgs84: Any) -> CrsChoice:
    (w, s, e, n), (clon, clat) = _bounds_and_centroid(aoi_wgs84)
    north = clat >= 0
    if abs(clat) > POLAR_LAT:
        epsg, nm = (3413, "WGS 84 / NSIDC Sea Ice Polar Stereographic North") if north else (3031, "WGS 84 / Antarctic Polar Stereographic")
        return CrsChoice(epsg, nm, "polar", None, "north" if north else "south",
                         [f"AOI centroid latitude {clat:.2f} is beyond 84 degrees: polar stereographic EPSG:{epsg} used (UTM is undefined there)"])
    zone = _utm_zone(clon, clat)
    epsg = (32600 if north else 32700) + zone
    warns: list[str] = []
    zw, ze = _utm_zone(w, clat), _utm_zone(math.nextafter(e, -math.inf), clat)
    if zw != ze:
        warns.append(f"AOI spans UTM zones {zw} and {ze}; the centroid zone {zone} is used for the whole AOI. "
                     "Scale distortion grows with distance from the zone central meridian, so metric values near the far edge are less accurate")
    return CrsChoice(epsg, f"WGS 84 / UTM zone {zone}{'N' if north else 'S'}", "utm", zone, "north" if north else "south", warns)


def _validate_user_crs(crs: str) -> CRS:
    try:
        c = CRS.from_user_input(crs)
    except Exception as exc:  # pyproj raises CRSError for unknown codes
        raise EnvError(f"unknown or invalid CRS {crs!r}") from exc
    if not c.is_projected:
        raise EnvError(f"CRS {crs!r} is not projected; a metric reference grid needs a projected CRS with metre units")
    if any(abs(a.unit_conversion_factor - 1.0) > 1e-9 or a.unit_name.lower() not in ("metre", "meter") for a in c.axis_info):
        raise EnvError(f"CRS {crs!r} does not use metre units")
    return c


def _snap(bounds: tuple[float, float, float, float], res: float) -> tuple[float, float, int, int]:
    l, b, r, t = bounds
    left, bottom = math.floor(l / res) * res, math.floor(b / res) * res
    right, top = math.ceil(r / res) * res, math.ceil(t / res) * res
    w, h = max(1, round((right - left) / res)), max(1, round((top - bottom) / res))
    return left, bottom + h * res, w, h  # (left, top, width, height)


def build_reference_grid(aoi_wgs84: Any, *, crs: str | None = None, resolution_m: float | None = None,
                         max_pixels: int = 16_000_000, default_resolution_m: float = 30.0) -> ReferenceGrid:
    (w, s, e, n), _ = _bounds_and_centroid(aoi_wgs84)
    res = default_resolution_m if resolution_m is None else resolution_m
    if not (isinstance(res, (int, float)) and math.isfinite(res) and res > 0):
        raise EnvError("resolution must be a positive number of metres")
    if max_pixels < 1:
        raise EnvError("max_pixels must be >= 1")
    warns: list[str] = []
    if crs is None:
        ch = choose_projected_crs(aoi_wgs84)
        pcrs, chosen = CRS.from_epsg(ch.epsg), "auto"
        warns += ch.warnings
    else:
        pcrs, chosen = _validate_user_crs(crs), "user"
    epsg = pcrs.to_epsg()
    tr = Transformer.from_crs(4326, pcrs, always_xy=True)
    bounds = tr.transform_bounds(w, s, e, n, densify_pts=21)
    if not all(math.isfinite(v) for v in bounds):
        raise EnvError("AOI cannot be projected into the chosen CRS (outside its area of use)")
    if (bounds[2] - bounds[0]) < res and (bounds[3] - bounds[1]) < res:
        warns.append(f"AOI ({bounds[2] - bounds[0]:.1f} x {bounds[3] - bounds[1]:.1f} m) is smaller than one {res:g} m cell; the grid is 1x1 cell")
    left, top, width, height = _snap(bounds, res)
    if width * height > max_pixels:
        orig = res
        while width * height > max_pixels:
            res *= max(2, math.ceil(math.sqrt(width * height / max_pixels)))
            left, top, width, height = _snap(bounds, res)
        warns.append(f"grid of {orig:g} m would exceed max_pixels={max_pixels}; resolution coarsened to {res:g} m (factor {res / orig:g})")
    tf = Affine(res, 0, left, 0, -res, top)
    crs_str = f"EPSG:{epsg}" if epsg else pcrs.to_wkt()
    return ReferenceGrid(TargetGrid(crs_str, tf, width, height), epsg, float(res),
                         (left, top - height * res, left + width * res, top), chosen, warns)


def _native_metres(meta, lon_lat: tuple[float, float] | None) -> tuple[float, float] | None:
    """Native pixel size in metres, or None when it cannot be stated honestly."""
    if meta.is_geographic:
        lon, lat = (meta.bounds[0] + meta.bounds[2]) / 2, (meta.bounds[1] + meta.bounds[3]) / 2
        g = Geod(ellps="WGS84")
        return g.inv(lon, lat, lon + meta.res_x, lat)[2], g.inv(lon, lat, lon, lat + meta.res_y)[2]
    f = CRS.from_user_input(meta.crs).axis_info[0].unit_conversion_factor
    return meta.res_x * f, meta.res_y * f


def align_layer_to_reference(src_path: str | Path, ref: ReferenceGrid, kind: LayerKind, dst_path: str | Path,
                             *, aoi_wgs84: Any = None) -> AlignedLayer:
    meta = inspect_raster(src_path)
    if meta.crs is None:
        raise EnvError(f"{meta.source_name}: CRS missing; refusing to guess one")
    g = ref.grid
    l, b, r, t = Transformer.from_crs(meta.crs, g.crs, always_xy=True).transform_bounds(*meta.bounds, densify_pts=21)
    if not all(math.isfinite(v) for v in (l, b, r, t)) or r <= ref.bounds[0] or l >= ref.bounds[2] or t <= ref.bounds[1] or b >= ref.bounds[3]:
        raise NotAvailable(f"{meta.source_name} does not overlap the reference grid")
    res = align_to_grid(src_path, g, kind)  # reuse: bilinear / nearest / circular aspect
    arr = res.array
    warns = list(res.warnings)
    if aoi_wgs84 is not None:
        geom = aoi_wgs84 if hasattr(aoi_wgs84, "geom_type") else box(*aoi_wgs84)
        poly = shp_transform(Transformer.from_crs(4326, g.crs, always_xy=True).transform, geom)
        arr = np.where(geometry_mask([poly], out_shape=arr.shape, transform=g.transform, all_touched=True), np.nan, arr).astype(np.float32)
    nm = _native_metres(meta, None)
    if nm and ref.resolution_m < 0.999 * min(nm):
        warns.append(f"OVERSAMPLING: grid {ref.resolution_m:g} m is finer than the source native resolution "
                     f"({nm[0]:.1f} x {nm[1]:.1f} m); values are interpolated/replicated, no detail is added")
    if not np.isfinite(arr).any():
        warns.append("no valid pixel on the reference grid (source is entirely nodata or has no valid data inside the AOI); reported, not filled")
    resampling = "nearest" if kind in CATEGORICAL_KINDS else ("circular_sincos" if kind in CIRCULAR_KINDS else "bilinear")
    tags = {**meta.tags, "source": meta.source_name, "resampling": resampling, **({"units": meta.units} if meta.units else {})}
    if kind in CATEGORICAL_KINDS:
        dt = np.dtype(meta.dtype)
        if not np.issubdtype(dt, np.integer):
            raise EnvError(f"{meta.source_name}: categorical raster must have an integer dtype, found {dt}")
        nd = meta.nodata if meta.nodata is not None and not np.isnan(meta.nodata) else int(np.iinfo(dt).max)
        if meta.nodata is None and (arr == nd).any():
            raise EnvError(f"{meta.source_name}: no nodata declared and dtype max is a class id")
        out = np.where(np.isfinite(arr), arr, nd).astype(dt)
        Path(dst_path).parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", driver="GTiff", height=g.height, width=g.width, count=1, dtype=dt, crs=g.crs,
                           transform=g.transform, nodata=nd, compress="deflate") as d:
            d.write(out, 1)
            d.update_tags(**{k: str(v) for k, v in tags.items()})
    else:
        write_geotiff(dst_path, arr, g.transform, g.crs, tags)
    q = layer_quality(arr, meta, processing_resolution={"x": ref.resolution_m, "y": ref.resolution_m, "unit": "metre"}, warnings=warns)
    q.crs = g.crs
    if nm:
        q.native_resolution = {**q.native_resolution, "approx_metre": {"x": nm[0], "y": nm[1]}}
    return AlignedLayer(Path(dst_path), q, resampling)
