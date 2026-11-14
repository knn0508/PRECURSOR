"""User-provided NDVI GeoTIFF (generic, or a MODIS MOD13/MYD13 NDVI layer) -> float32 NDVI on the metric target grid.

Scaling rule: a scale factor is applied ONLY when the file's own tags/scale metadata or the explicit `scale_factor=` option say
so. Otherwise values are taken as NDVI already. After any scaling every value must lie in [-1, 1]; values outside are
invalid (NaN, counted, reported), never clipped. Official MOD13Q1 v061 facts (scale 0.0001, fill -3000, valid range
-2000..10000, 16-day, 250 m): https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod13q1-061 . Descriptive only.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401  (must precede geo libraries)

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from affine import Affine

from app.services.environmental.external_inputs import (
    aoi_mask, aoi_quality, input_hash, origin_of, require_metric_grid,
)
from app.services.environmental.raster.alignment import TargetGrid, align_array
from app.services.environmental.raster.io import gdal_path, inspect_raster, write_geotiff
from app.services.environmental.types import (
    SYNTHETIC_TAG, EnvError, LayerKind, LayerQuality, LayerStatus, MeasurementKind, NotAvailable, Provenance,
)

_DATE_TAGS = ("observation_date", "OBSERVATION_DATE", "RANGEBEGINNINGDATE", "time", "TIME", "date", "DATE")


@dataclass
class NdviResult:
    path: Path
    quality: LayerQuality
    provenance: Provenance
    stats: dict[str, Any]
    status: LayerStatus
    warnings: list[str]
    input_hash: str
    observation: dict[str, str] = field(default_factory=dict)  # file name -> date/period string or "UNKNOWN"


def _observation(name: str, tags: dict[str, str]) -> str:
    for k in _DATE_TAGS:
        if tags.get(k):
            return str(tags[k])
    m = re.search(r"\.A(\d{4})(\d{3})(?!\d)", name) or re.search(r"(?<!\d)A(\d{4})(\d{3})(?!\d)", name)
    if m:
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%j").date().isoformat() + " (MODIS composite start, from file name)"
        except ValueError:
            pass
    m = re.search(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", name)
    return f"{m.group(0)} (from file name)" if m else "UNKNOWN"


def _tag(tags: dict[str, str], *names: str) -> str | None:
    low = {k.lower(): v for k, v in tags.items()}
    return next((low[n.lower()] for n in names if n.lower() in low), None)


def _read_ndvi(f: Path, scale_opt: float | None, warns: list[str]) -> tuple[np.ndarray, Any, dict]:
    """Native-resolution NDVI (NaN = invalid) plus counters. Masking happens BEFORE resampling."""
    meta = inspect_raster(f)
    if meta.crs is None:
        raise EnvError(f"{f.name}: CRS missing; refusing to guess one")
    with rasterio.open(gdal_path(f)) as ds:
        raw = ds.read(1).astype(np.float64)
        scales, offsets = ds.scales[0], ds.offsets[0]
    tags = meta.tags
    fill = _tag(tags, "_FillValue")
    fills = [float(fill)] if fill is not None else []
    if meta.nodata is not None and not np.isnan(meta.nodata):
        fills.append(float(meta.nodata))
    invalid = ~np.isfinite(raw)
    for fv in fills:
        invalid |= raw == fv
    n_fill = int((invalid & np.isfinite(raw)).sum())
    vr = _tag(tags, "valid_range")
    n_vr = 0
    if vr:
        lo, hi = (float(x) for x in re.split(r"[,\s]+", vr.strip("[]() ")) if x)
        bad = ~invalid & ((raw < lo) | (raw > hi))
        n_vr = int(bad.sum())
        invalid |= bad
    scale = scale_opt if scale_opt is not None else (float(_tag(tags, "scale_factor")) if _tag(tags, "scale_factor") else None)
    offset = float(_tag(tags, "add_offset") or 0.0)
    if scale is None and scales not in (None, 1.0):
        scale, offset = float(scales), float(offsets or 0.0)
    if scale is not None:
        raw = raw * scale + offset
    elif re.match(r"(?i)m[oy]d13", f.name):
        warns.append(f"{f.name}: name looks like MOD13/MYD13 but no scale_factor tag/option: values treated as NDVI already")
    out_of_range = ~invalid & ((raw < -1.0) | (raw > 1.0))
    n_oor = int(out_of_range.sum())
    invalid |= out_of_range
    raw[invalid] = np.nan
    if n_oor:
        warns.append(f"{f.name}: {n_oor} value(s) outside [-1, 1] treated as invalid (not clipped)")
    return raw.astype(np.float32), meta, {"scale_applied": scale, "add_offset": offset if scale is not None else None,
                                         "n_fill": n_fill, "n_outside_valid_range": n_vr, "n_out_of_range": n_oor}


def process_ndvi(files: list[Path], aoi: Any, grid: TargetGrid, out_dir: Path, *, scale_factor: float | None = None) -> NdviResult:
    require_metric_grid(grid)
    files = sorted(Path(f) for f in files)
    if not files:
        raise NotAvailable("no NDVI input covers the AOI")
    inside, warns = aoi_mask(aoi, grid)
    acc = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
    obs: dict[str, str] = {}
    counters: dict[str, Any] = {}
    synthetic = False
    native = None
    for f in files:
        arr, meta, c = _read_ndvi(f, scale_factor, warns)
        res = align_array(arr, Affine(*meta.transform), meta.crs, meta.resolution(), grid, LayerKind.NDVI)
        acc = np.where(np.isnan(acc), res.array, acc)
        obs[f.name] = _observation(f.name, meta.tags)
        counters[f.name] = c
        synthetic |= bool(meta.tags.get(SYNTHETIC_TAG))
        native = meta.resolution()
    v = acc[inside & np.isfinite(acc)]
    if v.size == 0:
        raise NotAvailable("NDVI input has no valid pixel inside the AOI (valid 0%: outside coverage or all nodata/invalid); nothing written")
    tags = {"units": "NDVI (dimensionless)", "source": ";".join(f.name for f in files), "resampling": "bilinear",
            "observation": "; ".join(sorted(set(obs.values())))}
    if synthetic:
        tags[SYNTHETIC_TAG] = "1"
    path = write_geotiff(Path(out_dir) / "ndvi.tif", acc, grid.transform, grid.crs, tags)
    q = aoi_quality(acc, inside, grid, native, passed=["values within [-1, 1] after declared scaling", "no clipping"], failed=[], warnings=warns)
    stats = {"mean": float(v.mean()), "min": float(v.min()), "max": float(v.max()), "std": float(v.std()),
             "valid_percent": q.valid_percent, "n_valid_pixels": int(v.size), "observation": dict(obs),
             "per_file": counters, "n_out_of_range": sum(c["n_out_of_range"] for c in counters.values()), "crs": grid.crs}
    prov = Provenance(provider="USER_NDVI", dataset_name="user-provided NDVI / MODIS vegetation index", origin=origin_of(synthetic),
                      measurement_kind=MeasurementKind.SOURCE_OBSERVATION, source_files=[f.name for f in files],
                      units="NDVI (dimensionless)", method="declared scaling only; invalid masked before bilinear resampling onto grid",
                      notes=[f"observation: {o}" for o in obs.values()])
    status = LayerStatus.PROCESSED if q.valid_percent == 100.0 and not stats["n_out_of_range"] else LayerStatus.PARTIALLY_PROCESSED
    return NdviResult(path, q, prov, stats, status, warns, input_hash(files, grid, aoi, {"scale_factor": scale_factor}), obs)
