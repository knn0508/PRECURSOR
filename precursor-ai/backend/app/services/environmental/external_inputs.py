"""Shared helpers for USER-PROVIDED layers (lithology, NDVI, distance-to-river/fault/road) in data/external/<subdir>/.

Vector inputs are GeoJSON only (no geopandas/fiona/pyogrio installed). Nothing here downloads or reads outside data/external.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401  (must precede geo libraries)

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.features import geometry_mask
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
import shapely

from app.services.environmental.providers.base import aoi_bounds, raster_covers
from app.services.environmental.raster.alignment import TargetGrid
from app.services.environmental.storage import external_dir
from app.services.environmental.types import SYNTHETIC_TAG, DataOrigin, EnvError, LayerQuality

RASTER_SUFFIXES = (".tif", ".tiff")
VECTOR_SUFFIXES = (".geojson", ".json")
_NON_GEOJSON = (".shp", ".gpkg", ".kml", ".gml", ".fgb")


def is_legend_file(p: Path) -> bool:
    return p.name.lower().endswith(".legend.json")


def read_geojson(path: Path) -> tuple[list[BaseGeometry | None], list[dict], str, bool]:
    """GeoJSON -> (geometries, properties, crs string, is_synthetic). CRS is EPSG:4326 unless a legacy `crs` member says
    otherwise (honoured explicitly). Geometries that cannot be built come back as None (counted by the caller)."""
    if path.suffix.lower() in _NON_GEOJSON:
        raise EnvError(f"{path.name}: only GeoJSON vectors are supported (Shapefile/GeoPackage need a dependency that is not approved)")
    if path.suffix.lower() not in VECTOR_SUFFIXES:
        raise EnvError(f"{path.name}: unsupported vector format; use .geojson or .json")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EnvError(f"{path.name}: not readable as JSON ({exc})") from exc
    if not isinstance(doc, dict) or "type" not in doc:
        raise EnvError(f"{path.name}: not a GeoJSON object")
    crs = "EPSG:4326"
    if isinstance(doc.get("crs"), dict):
        name = (doc["crs"].get("properties") or {}).get("name")
        try:
            crs = CRS.from_user_input(name).to_string()
        except Exception as exc:  # pyproj raises CRSError (and ValueError for None)
            raise EnvError(f"{path.name}: unreadable crs member {name!r}") from exc
    t = doc["type"]
    feats = doc.get("features", []) if t == "FeatureCollection" else [doc] if t == "Feature" else [{"geometry": doc, "properties": {}}]
    synthetic = bool((doc.get("properties") or {}).get("synthetic") or doc.get("synthetic"))
    geoms: list[BaseGeometry | None] = []
    props: list[dict] = []
    for f in feats:
        try:
            g = shape(f["geometry"]) if f.get("geometry") else None
        except (ValueError, TypeError, KeyError, AttributeError):
            g = None
        geoms.append(g)
        props.append(dict(f.get("properties") or {}))
    return geoms, props, crs, synthetic


def to_grid_crs(geom: BaseGeometry, src_crs: str, grid: TargetGrid) -> BaseGeometry:
    """Explicit pyproj transform of a geometry into the grid CRS (vertices only; straight edges in the target CRS)."""
    tr = Transformer.from_crs(src_crs, grid.crs, always_xy=True)
    return shapely.transform(geom, lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1])))


def require_metric_grid(grid: TargetGrid) -> CRS:
    crs = CRS.from_user_input(grid.crs)
    if crs.is_geographic or not crs.is_projected:
        raise EnvError(f"grid CRS {grid.crs} is geographic/not projected: distances and metre grids need a projected CRS")
    if not all(a.unit_name in ("metre", "meter") for a in crs.axis_info):
        raise EnvError(f"grid CRS {grid.crs} is not metre-based")
    return crs


def aoi_mask(aoi: Any, grid: TargetGrid) -> tuple[np.ndarray, list[str]]:
    """Boolean (height, width) mask of grid pixels whose centre is inside the AOI (falls back to touched pixels when the
    AOI is smaller than one pixel, and says so)."""
    poly = to_grid_crs(aoi, "EPSG:4326", grid)
    shape_ = (grid.height, grid.width)
    inside = ~geometry_mask([poly], out_shape=shape_, transform=grid.transform, all_touched=False)
    if inside.any():
        return inside, []
    inside = ~geometry_mask([poly], out_shape=shape_, transform=grid.transform, all_touched=True)
    if not inside.any():
        raise EnvError("AOI does not intersect the target grid")
    return inside, ["AOI is smaller than one grid pixel; the touched pixel(s) are used (resolution not increased)"]


def discover_external(data_root: Path, subdir: str, aoi: Any, suffixes: tuple[str, ...], *, vector_buffer_deg: float = 0.0) -> list[Path]:
    """Files in data/external/<subdir>/ whose extent intersects the AOI. Never raises for a missing/empty directory.
    Legend sidecars (*.legend.json) are never returned as inputs."""
    try:
        d = external_dir(data_root, subdir)
        root = (data_root / "external").resolve()
        if not d.is_dir():
            return []
        w, s, e, n = aoi_bounds(aoi)
    except (ValueError, EnvError, OSError):
        return []
    out: list[Path] = []
    for p in sorted(d.iterdir()):
        if not p.is_file() or p.suffix.lower() not in suffixes or is_legend_file(p) or not p.resolve().is_relative_to(root):
            continue
        try:
            if p.suffix.lower() in RASTER_SUFFIXES:
                ok = raster_covers(p, (w, s, e, n))
            else:
                geoms, _, crs, _ = read_geojson(p)
                tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
                bs = [g.bounds for g in geoms if g is not None and not g.is_empty]
                if not bs:
                    continue
                xs = [tr.transform(b[0], b[1]) for b in bs] + [tr.transform(b[2], b[3]) for b in bs]
                l, r = min(x[0] for x in xs), max(x[0] for x in xs)
                b_, t = min(x[1] for x in xs), max(x[1] for x in xs)
                v = vector_buffer_deg
                ok = not (r < w - v or l > e + v or t < s - v or b_ > n + v)
        except EnvError:
            continue
        if ok:
            out.append(p)
    return out


def input_hash(files: list[Path], grid: TargetGrid, aoi: Any, options: dict[str, Any]) -> str:
    payload = {"files": sorted((f.name, f.stat().st_size) for f in files), "grid": [grid.crs, list(grid.transform)[:6], grid.width, grid.height],
               "aoi": aoi.wkt, "options": options}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def raster_is_synthetic(path: Path) -> bool:
    with rasterio.open(path) as ds:
        return bool(ds.tags().get(SYNTHETIC_TAG))


def origin_of(synthetic: bool) -> DataOrigin:
    return DataOrigin.SYNTHETIC_FIXTURE if synthetic else DataOrigin.LOCAL_UNVERIFIED


def write_class_geotiff(path: Path, arr: np.ndarray, transform, crs: str, tags: dict[str, str], nodata: int = 65535) -> Path:
    """uint16 class raster with a declared nodata (65535). `arr` is float with NaN = missing, or integer ids."""
    out = np.full(arr.shape, nodata, dtype=np.uint16)
    ok = np.isfinite(arr)
    if ok.any() and (arr[ok].min() < 0 or arr[ok].max() >= nodata or not np.all(arr[ok] == np.round(arr[ok]))):
        raise EnvError(f"class ids must be integers in 0..{nodata - 1} to be written as uint16")
    out[ok] = arr[ok].astype(np.uint16)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype="uint16", crs=crs,
                       transform=transform, nodata=nodata, compress="deflate") as ds:
        ds.write(out, 1)
        ds.update_tags(**{k: str(v) for k, v in tags.items()})
    return Path(path)


def aoi_quality(values: np.ndarray, aoi_in: np.ndarray, grid: TargetGrid, native: dict | None, *, passed: list[str],
                failed: list[str], warnings: list[str], temporal: str | None = None) -> LayerQuality:
    """Pixel accounting over AOI pixels only. `values` is the full grid array (NaN = missing)."""
    total = int(aoi_in.sum())
    valid = int(np.isfinite(values[aoi_in]).sum())
    vp = round(100.0 * valid / total, 4)
    res = grid.resolution()
    res["unit"] = "metre"
    return LayerQuality(total_pixels=total, valid_pixels=valid, valid_percent=vp, missing_percent=round(100.0 - vp, 4),
                        aoi_coverage_percent=vp, native_resolution=native, processing_resolution=res, crs=grid.crs,
                        temporal_start=temporal, temporal_end=temporal, checks_passed=passed, checks_failed=failed, warnings=list(warnings))
