"""Local land-cover GeoTIFF(s) -> class distribution over the AOI window. Native pixels only (nearest semantics: class ids are
never averaged or resampled). Percentages are of VALID AOI pixels (nodata/NaN excluded). No risk labels."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import json

import numpy as np
import rasterio
from rasterio.merge import merge

from app.services.environmental.providers.base import clip_raster, aoi_bounds, raster_origin, write_clip_geotiff
from app.services.environmental.providers.land_cover import LICENCE, VERSIONS, WORLDCOVER_LEGEND
from app.services.environmental.types import (
    SYNTHETIC_TAG, DataOrigin, EnvError, LayerQuality, MeasurementKind, NotAvailable, Provenance,
)


@dataclass
class LandCoverResult:
    classes: list[dict[str, Any]]  # known classes: id, name, color, pixels, percent
    unknown_classes: list[dict[str, Any]]  # ids not in the official legend: id, pixels, percent (never dropped)
    valid_pixels: int
    total_pixels: int
    version: str
    year: int
    quality: LayerQuality
    provenance: Provenance
    warnings: list[str] = field(default_factory=list)
    rasters: list[dict[str, Any]] = field(default_factory=list)  # clipped class rasters (only when out_dir is given)


def process_land_cover(files: list[Path], aoi: Any, *, version: str = "v200", out_dir: Path | None = None) -> LandCoverResult:
    if version not in VERSIONS:
        raise ValueError(f"unknown WorldCover version {version!r}")
    bbox = aoi_bounds(aoi)
    counts: dict[int, int] = {}
    warnings: list[str] = []
    total = valid = 0
    cov = 0.0
    origins: set[DataOrigin] = set()
    used: list[str] = []
    clips: list[tuple[str, Any]] = []
    res = crs = None
    for f in sorted(files):
        try:
            c = clip_raster(f, bbox, aoi)
        except NotAvailable as e:
            warnings.append(str(e))
            continue
        warnings.extend(c.warnings)
        d = c.data
        if np.issubdtype(d.dtype, np.floating):
            non_int = d.compressed()
            if non_int.size and not np.all(non_int == np.round(non_int)):
                raise EnvError(f"{f.name}: land-cover raster holds non-integer values (was it resampled?)")
        if c.nodata is None:
            warnings.append(f"{f.name}: no nodata declared; no pixel treated as missing")
        ids, n = np.unique(d.compressed().astype("int64"), return_counts=True)
        for i, k in zip(ids, n):
            counts[int(i)] = counts.get(int(i), 0) + int(k)
        total += int(d.size)
        valid += int(d.count())
        cov += c.coverage
        origins.add(raster_origin(f))
        used.append(f.name)
        clips.append((f.name, c))
        res, crs = {"x": c.resolution[0], "y": c.resolution[1], "unit": "CRS units"}, c.crs
    if not used:
        raise NotAvailable("no local land-cover raster covers the AOI")
    if valid == 0:
        raise EnvError("all land-cover pixels in the AOI are nodata")
    year = VERSIONS[version]
    pct = lambda k: round(100.0 * k / valid, 6)  # noqa: E731
    classes = [{"class_id": i, "name": WORLDCOVER_LEGEND[i][0], "color": WORLDCOVER_LEGEND[i][1], "pixels": k, "percent": pct(k)}
               for i, k in sorted(counts.items()) if i in WORLDCOVER_LEGEND]
    unknown = [{"class_id": i, "pixels": k, "percent": pct(k)} for i, k in sorted(counts.items()) if i not in WORLDCOVER_LEGEND]
    if unknown:
        warnings.append(f"class ids not in the official WorldCover legend: {[u['class_id'] for u in unknown]}")
    origin = DataOrigin.SYNTHETIC_FIXTURE if DataOrigin.SYNTHETIC_FIXTURE in origins else DataOrigin.LOCAL_UNVERIFIED
    cov = min(cov, 1.0)
    q = LayerQuality(total_pixels=total, valid_pixels=valid, valid_percent=round(100 * valid / total, 4),
                     missing_percent=round(100 * (total - valid) / total, 4), aoi_coverage_percent=round(100 * cov, 4),
                     native_resolution=res, crs=crs, temporal_start=f"{year}-01-01", temporal_end=f"{year}-12-31",
                     warnings=list(warnings), checks_passed=["raster readable", "no resampling applied"])
    prov = Provenance(provider="WORLDCOVER", dataset_name="ESA WorldCover", dataset_version=f"{version} ({year})", origin=origin,
                      measurement_kind=MeasurementKind.STATISTICAL_SUMMARY, source_files=used, units="class id; percent of valid pixels",
                      method="native-pixel window clip masked to the AOI polygon (bbox when only a bbox is given); counts of class ids", nodata=None,
                      notes=[f"licence: {LICENCE}", "modelled/classified product, accuracy not assessed here"])
    rasters = _write_rasters(clips, Path(out_dir), version, year, warnings) if out_dir is not None else []
    return LandCoverResult(classes, unknown, valid, total, version, year, q, prov, warnings, rasters)


def _write_rasters(clips: list[tuple[str, Any]], out_dir: Path, version: str, year: int, warnings: list[str]) -> list[dict[str, Any]]:
    """Native-grid class rasters, no resampling, integer dtype + declared nodata kept. One land_cover.tif when all tiles share
    CRS/resolution/dtype/nodata and are pixel-aligned (mosaic by copy), else one file per tile (said in warnings)."""
    legend = json.dumps({str(k): {"name": v[0], "color": v[1]} for k, v in WORLDCOVER_LEGEND.items()}, sort_keys=True)
    base = {"legend": legend, "version": version, "year": str(year), "source": ",".join(n for n, _ in clips)}

    def tags(c: Any) -> dict[str, str]:
        return {**base, **{k: v for k, v in c.tags.items() if k == SYNTHETIC_TAG}}

    def compatible(a: Any, b: Any) -> bool:
        ta, tb = a.transform, b.transform
        fx, fy = (tb.c - ta.c) / ta.a, (tb.f - ta.f) / ta.e
        aligned = abs(fx - round(fx)) < 1e-6 and abs(fy - round(fy)) < 1e-6
        return a.nodata is not None and (a.crs, a.dtype, a.nodata, tuple(a.resolution)) == (b.crs, b.dtype, b.nodata, tuple(b.resolution)) and aligned

    entry = lambda p, names: {"path": str(p), "name": p.name, "sources": names, "version": version, "year": year}  # noqa: E731
    if len(clips) == 1 or all(compatible(clips[0][1], c) for _, c in clips[1:]):
        first = clips[0][1]
        if len(clips) == 1:
            merged = first
        else:
            from rasterio.io import MemoryFile
            mems, srcs = [], []
            try:
                for _, c in clips:  # each clip as an in-memory dataset for rasterio.merge (method 'first': copy, no resampling)
                    mf = MemoryFile()
                    with mf.open(driver="GTiff", height=c.data.shape[0], width=c.data.shape[1], count=1, dtype=c.dtype, crs=c.crs,
                                 transform=c.transform, nodata=c.nodata) as d:
                        d.write(np.ma.filled(c.data, c.nodata), 1)
                    mems.append(mf)
                    srcs.append(mf.open())
                arr, tr = merge(srcs, nodata=first.nodata, method="first")
            finally:
                for s_ in srcs:
                    s_.close()
                for m_ in mems:
                    m_.close()
            data = np.ma.masked_equal(arr[0], first.nodata)
            merged = replace(first, data=data, transform=tr)
            warnings.append("land-cover tiles merged into one raster (same CRS/resolution/grid; values copied, not resampled)")
        p = write_clip_geotiff(merged, out_dir / "land_cover.tif", tags=tags(first))
        return [entry(p, [n for n, _ in clips])]
    warnings.append("land-cover tiles differ in CRS/resolution/grid/dtype; one raster per tile written, not merged")
    out = []
    for n, c in clips:
        out.append(entry(write_clip_geotiff(c, out_dir / f"land_cover_{Path(n).stem}.tif", tags=tags(c)), [n]))
    return out
