"""Descriptive terrain statistics for an AOI. STATISTICAL_SUMMARY only: no classes, labels, thresholds or scores."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from app.services.environmental.dem.aspect import SECTOR_LABELS, circular_mean_deg, resultant_length, sector_histogram
from app.services.environmental.raster.clipping import clip_raster
from app.services.environmental.raster.io import read_float
from app.services.environmental.types import MeasurementKind

SLOPE_BIN_EDGES_DEG = list(range(0, 95, 5))  # 0-5, 5-10, ... 85-90 (plain numeric bins, no named classes)


def _load(path, aoi):
    if aoi is None:
        arr, meta = read_float(path)
        return arr, meta.units
    res = clip_raster(path, aoi)
    return res.array, res.tags.get("units")


def _f(v) -> float | None:
    return None if v is None or not np.isfinite(v) else float(v)


def terrain_features(elevation_path: str | Path, slope_path: str | Path, aspect_path: str | Path, aoi=None) -> dict:
    """Features as {name: {"value", "unit"}} plus counts and warnings. `aoi` (EPSG:4326 polygon) restricts all statistics;
    None uses the whole rasters. Empty data gives None values (never 0) and a warning."""
    z, z_units = _load(elevation_path, aoi)
    s, _ = _load(slope_path, aoi)
    a, _ = _load(aspect_path, aoi)
    warns: list[str] = []
    if z_units is None:
        warns.append("elevation units not declared in the file tags")
    zv, sv, av = z[np.isfinite(z)], s[np.isfinite(s)], a[np.isfinite(a)]
    if zv.size == 0:
        warns.append("no valid elevation pixels in the AOI")
    if sv.size == 0:
        warns.append("no valid slope pixels in the AOI")
    flat = int((np.isfinite(s) & ~np.isfinite(a)).sum())
    feats = {
        "elevation_mean": {"value": _f(zv.mean()) if zv.size else None, "unit": z_units},
        "elevation_min": {"value": _f(zv.min()) if zv.size else None, "unit": z_units},
        "elevation_max": {"value": _f(zv.max()) if zv.size else None, "unit": z_units},
        "elevation_range": {"value": _f(zv.max() - zv.min()) if zv.size else None, "unit": z_units},
        "slope_mean": {"value": _f(sv.mean()) if sv.size else None, "unit": "degree"},
        "slope_max": {"value": _f(sv.max()) if sv.size else None, "unit": "degree"},
        "slope_histogram": {"value": {"bin_edges_deg": SLOPE_BIN_EDGES_DEG,
                                      "counts": np.histogram(sv, bins=SLOPE_BIN_EDGES_DEG)[0].astype(int).tolist()},
                            "unit": "pixel_count"},
        "aspect_sector_counts": {"value": sector_histogram(a), "unit": "pixel_count", "sectors": list(SECTOR_LABELS)},
        "aspect_circular_mean": {"value": _f(circular_mean_deg(av)), "unit": "degree_clockwise_from_north"},
        "aspect_resultant_length": {"value": _f(resultant_length(av)), "unit": "dimensionless_0_1"},
    }
    return {"features": feats, "valid_pixel_count": int(zv.size), "valid_slope_pixel_count": int(sv.size),
            "flat_pixel_count": flat, "measurement_kind": MeasurementKind.STATISTICAL_SUMMARY.value, "warnings": warns}
