"""Per-layer raster quality figures and structural validation. Missing data is NaN and is reported, never zero-filled."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np

from app.services.environmental.raster.io import RasterMeta, read_float
from app.services.environmental.types import LayerQuality


def layer_quality(
    arr: np.ndarray, meta: RasterMeta, *, aoi_coverage_percent: float | None = None,
    processing_resolution: dict | None = None, checks_passed: Iterable[str] = (), checks_failed: Iterable[str] = (),
    warnings: Iterable[str] = (),
) -> LayerQuality:
    """Pixel accounting: valid = finite. Percentages are 0-100; an empty array gives None, not 0."""
    total = int(arr.size)
    valid = int(np.isfinite(arr).sum())
    vp = round(100.0 * valid / total, 4) if total else None
    return LayerQuality(
        total_pixels=total, valid_pixels=valid, valid_percent=vp, missing_percent=None if vp is None else round(100.0 - vp, 4),
        aoi_coverage_percent=aoi_coverage_percent, native_resolution=meta.resolution(),
        processing_resolution=processing_resolution or meta.resolution(), crs=meta.crs,
        checks_passed=list(checks_passed), checks_failed=list(checks_failed), warnings=list(warnings) + list(meta.notes))


def structural_checks(arr: np.ndarray, meta: RasterMeta) -> tuple[list[str], list[str], list[str]]:
    """(passed, failed, warnings) for CRS, dimensions, geotransform, finiteness and nodata handling."""
    ok: list[str] = []
    bad: list[str] = []
    warn: list[str] = []
    (bad if meta.crs is None else ok).append("crs_present_and_valid" if meta.crs else f"crs_missing: {meta.crs_error}")
    (ok if meta.width > 0 and meta.height > 0 else bad).append("dimensions_positive")
    a, b, c, d, e, f = meta.transform
    det = a * e - b * d
    nondeg = all(np.isfinite([a, b, c, d, e, f])) and a != 0 and e != 0 and det != 0
    (ok if nondeg else bad).append("geotransform_non_degenerate")
    if np.isinf(arr).any():
        bad.append("values_finite: +/-inf present")
    else:
        ok.append("values_finite")
    if meta.nodata is None and meta.dtype.startswith(("int", "uint")):
        warn.append("integer raster declares no nodata value: missing pixels cannot be distinguished from data")
    else:
        ok.append("nodata_handling")
    if not np.isfinite(arr).any():
        bad.append("has_valid_pixels: every pixel is nodata")
    else:
        ok.append("has_valid_pixels")
    return ok, bad, warn


def validate_raster(path: str | Path, *, aoi_coverage_percent: float | None = None) -> LayerQuality:
    arr, meta = read_float(path)
    ok, bad, warn = structural_checks(arr, meta)
    return layer_quality(arr, meta, aoi_coverage_percent=aoi_coverage_percent, checks_passed=ok, checks_failed=bad, warnings=warn)
