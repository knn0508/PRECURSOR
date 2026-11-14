"""DEM preparation (mosaic -> clip -> elevation.tif) and terrain derivation (slope.tif, aspect.tif).

Memory bound: tiles are read whole (1x1 degree 1-arc-second = ~52 MB float32); slope/aspect gradients are computed in
512-row bands but the output arrays are whole-grid float32. Fine for tile-to-AOI scale; not for continental rasters.

Units/datum policy: elevation units come from the file tags; when absent they are ASSUMED metres for HGT/NASADEM-style
sources and the assumption is reported. A declared non-metre unit is rejected (no silent conversion). The vertical
reference is recorded as UNVERIFIED-from-file: NASADEM documentation says heights are geoid-referenced (EGM96 per the
product documentation; the model name was not confirmed on the NASA catalog page), but a file does not prove it.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from affine import Affine

from app.services.environmental.dem.aspect import FLAT_EPS_DEG, aspect_from_gradients
from app.services.environmental.dem.slope import slope_from_gradients, terrain_gradients
from app.services.environmental.raster.clipping import clip_array
from app.services.environmental.raster.io import inspect_raster, read_float, write_geotiff
from app.services.environmental.raster.mosaic import mosaic_rasters
from app.services.environmental.raster.quality import layer_quality, structural_checks
from app.services.environmental.types import SYNTHETIC_TAG, EnvError, LayerQuality, NotAvailable

_METRE = {"m", "metre", "metres", "meter", "meters"}
VERTICAL_NOTE = ("NASADEM docs: heights in metres relative to a geoid (EGM96 per product docs; NOT verified from the file)")


@dataclass
class DemResult:
    elevation_path: Path
    quality: LayerQuality
    warnings: list[str]
    native_resolution: dict
    units: str
    tiles_used: list[str]
    aoi_coverage_percent: float
    is_synthetic: bool
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class TerrainResult:
    slope_path: Path
    aspect_path: Path
    slope_quality: LayerQuality
    aspect_quality: LayerQuality
    flat_count: int
    warnings: list[str]
    is_synthetic: bool


def _resolve_units(units: str | None, nasadem_like: bool) -> tuple[str, list[str]]:
    if units is None:
        return "metre", [f"elevation units not declared; metres ASSUMED ({'HGT/NASADEM convention' if nasadem_like else 'no evidence'})"]
    if units.strip().lower() in _METRE:
        return "metre", []
    raise EnvError(f"elevation units {units!r} are not metres; refusing to convert silently")


def prepare_dem(tile_paths: list[str | Path], aoi_wgs84, out_dir: str | Path, **mosaic_kwargs) -> DemResult:
    """Mosaic (if >1 tile) -> clip to AOI -> `elevation.tif`. NotAvailable if no tiles or no AOI overlap."""
    if not tile_paths:
        raise NotAvailable("no DEM tiles supplied")
    out = Path(out_dir)
    mos = mosaic_rasters(list(tile_paths), **mosaic_kwargs)  # single tile passes through the same checks
    clip = clip_array(mos.array, mos.transform, mos.crs, aoi_wgs84)
    nasadem_like = any(m.source_kind.endswith("hgt") for m in mos.meta)
    units, uw = _resolve_units(mos.tags.get("units"), nasadem_like)
    if nasadem_like and not uw:
        uw.append("elevation units 'm' come from the GDAL HGT driver convention, not from NASADEM product metadata (ASSUMED)")
    tags = {**mos.tags, "units": units, "aoi_coverage_percent": str(clip.coverage_percent),
            "vertical_reference_note": VERTICAL_NOTE if nasadem_like else "vertical datum not declared; unknown"}
    path = write_geotiff(out / "elevation.tif", clip.array, clip.transform, clip.crs, tags)
    meta = inspect_raster(path)
    ok, bad, w = structural_checks(clip.array, meta)
    warns = list(mos.warnings) + clip.warnings + uw + w
    q = layer_quality(clip.array, meta, aoi_coverage_percent=clip.coverage_percent, checks_passed=ok, checks_failed=bad,
                      warnings=warns)
    return DemResult(path, q, warns, mos.native_resolution, units, mos.tiles_used, clip.coverage_percent,
                     tags.get(SYNTHETIC_TAG) == "1", tags)


def compute_terrain(elevation_path: str | Path, out_dir: str | Path) -> TerrainResult:
    """slope.tif and aspect.tif (degrees), on exactly the DEM grid. Elevation must be in metres."""
    z, meta = read_float(elevation_path)
    if meta.crs is None:
        raise EnvError(f"{meta.source_name}: CRS missing; cannot derive terrain")
    units, uw = _resolve_units(meta.units, False)
    t = Affine(*meta.transform)
    gx, gy = terrain_gradients(z, meta.crs, t)
    slope = slope_from_gradients(gx, gy)
    asp = aspect_from_gradients(gx, gy)
    base = {"source": meta.source_name, "units": "degree", "method": "Horn 3x3",
            "elevation_units": units,
            "cell_size": "ellipsoidal metres per row (geographic CRS)" if meta.is_geographic else "CRS linear unit -> metres",
            "nodata_policy": "NaN; border and NaN-neighbour cells are NaN, never 0"}
    if meta.is_synthetic:
        base[SYNTHETIC_TAG] = "1"
    out = Path(out_dir)
    sp = write_geotiff(out / "slope.tif", slope, t, meta.crs, {**base, "measurement": "slope, degrees from horizontal"})
    ap = write_geotiff(out / "aspect.tif", asp.aspect, t, meta.crs, {
        **base, "measurement": "aspect, degrees clockwise from north, downslope direction; flat/undefined = NaN",
        "flat_epsilon_degrees": str(FLAT_EPS_DEG), "flat_count": str(asp.flat_count)})
    warns = ["one-pixel border and cells next to nodata are NaN (Horn needs a full 3x3 window)"] + uw
    if asp.flat_count:
        warns.append(f"{asp.flat_count} flat cells (slope < {FLAT_EPS_DEG} deg) have undefined aspect (NaN)")
    qs, qa = (layer_quality(a, inspect_raster(p), warnings=warns, checks_passed=structural_checks(a, inspect_raster(p))[0],
                            checks_failed=structural_checks(a, inspect_raster(p))[1])
              for a, p in ((slope, sp), (asp.aspect, ap)))
    return TerrainResult(sp, ap, qs, qa, asp.flat_count, warns, meta.is_synthetic)
