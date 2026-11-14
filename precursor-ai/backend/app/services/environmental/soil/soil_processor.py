"""Local SoilGrids GeoTIFFs -> per property/depth/statistic AOI statistics. Descriptive only; no scores.

Raw (mapped integer) and converted (conventional) values are both kept. Conversion = raw / documented ISRIC factor.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

from app.services.environmental.providers.base import BBox, aoi_bounds, clip_raster, raster_origin, write_clip_geotiff
from app.services.environmental.providers.soilgrids import parse_soil_filename, units_for
from app.services.environmental.types import (
    DataOrigin, EnvError, LayerQuality, MeasurementKind, NotAvailable, Provenance,
)


@dataclass
class SoilResult:
    layers: list[dict[str, Any]]
    quality: LayerQuality
    provenance: Provenance
    warnings: list[str] = field(default_factory=list)
    rasters: list[dict[str, Any]] = field(default_factory=list)  # clipped converted-value GeoTIFFs (only when out_dir is given)


def _stats(a: np.ndarray, factor: float) -> dict[str, float | None]:
    if a.size == 0:
        return {"mean": None, "min": None, "max": None}
    return {"mean": float(a.mean()) / factor, "min": float(a.min()) / factor, "max": float(a.max()) / factor}


def process_soil(files: list[Path], aoi: Any, *, properties: set[str] | None = None,
                 out_dir: Path | None = None) -> SoilResult:
    bbox: BBox = aoi_bounds(aoi)
    layers: list[dict[str, Any]] = []
    rasters: list[dict[str, Any]] = []
    warnings: list[str] = []
    origins: set[DataOrigin] = set()
    tot = val = 0
    cov, crss, res = 1.0, set(), None
    for f in sorted(files):
        meta = parse_soil_filename(f.name)
        if meta is None:
            warnings.append(f"{f.name}: not a SoilGrids layer file name, ignored")
            continue
        if properties and meta["property"] not in properties:
            continue
        try:
            clip = clip_raster(f, bbox, aoi)
        except NotAvailable as e:
            warnings.append(str(e))
            continue
        warnings.extend(clip.warnings)
        src_units, factor, conv_units = units_for(meta["property"], meta["statistic"])
        if clip.nodata is None:
            warnings.append(f"{f.name}: file declares no nodata; every pixel treated as valid")
        valid = clip.data.compressed().astype("float64")
        total = int(clip.data.size)
        raw = _stats(valid, 1.0)
        layers.append({
            **meta, "source_units": src_units, "scale_factor": factor, "converted_units": conv_units,
            "nodata": clip.nodata, "raw_stats": raw, "converted_stats": _stats(valid, float(factor)),
            "total_pixels": total, "valid_pixels": int(valid.size),
            "valid_percent": round(100.0 * valid.size / total, 4) if total else None,
            "aoi_coverage_percent": round(100 * clip.coverage, 4), "file": f.name, "crs": clip.crs,
        })
        origins.add(raster_origin(f))
        if out_dir is not None:
            # CONVERTED values (raw / factor) on the native grid; masked/nodata -> NaN, never 0.
            conv = np.ma.masked_array(np.ma.filled(clip.data.astype("float32"), np.nan) / np.float32(factor), mask=np.ma.getmaskarray(clip.data))
            name = f"soil_{meta['property']}_{meta['top_cm']}-{meta['bottom_cm']}cm_{meta['statistic']}.tif"
            tags = {"units": conv_units, "scale_factor": str(factor), "raw_units": src_units, "property": meta["property"],
                    "statistic": meta["statistic"], "source": f.name}
            p = write_clip_geotiff(replace(clip, data=conv, dtype="float32", nodata=float("nan")), Path(out_dir) / name, tags=tags)
            rasters.append({"path": str(p), "property": meta["property"], "top_cm": meta["top_cm"], "bottom_cm": meta["bottom_cm"],
                            "statistic": meta["statistic"], "units": conv_units})
        tot += total
        val += int(valid.size)
        cov = min(cov, clip.coverage)
        crss.add(clip.crs)
        res = {"x": clip.resolution[0], "y": clip.resolution[1], "unit": "CRS units"}
    if not layers:
        raise NotAvailable("no usable local SoilGrids layer covers the AOI")
    if len(origins) > 1 or DataOrigin.SYNTHETIC_FIXTURE in origins:
        # Mixed or synthetic: never present as anything better than the weakest input.
        origin = DataOrigin.SYNTHETIC_FIXTURE
        if len(origins) > 1:
            warnings.append("inputs mix synthetic and non-synthetic files")
    else:
        origin = DataOrigin.LOCAL_UNVERIFIED
    if tot and val == 0:
        raise EnvError("all pixels in the AOI are nodata for every soil layer")
    q = LayerQuality(total_pixels=tot, valid_pixels=val, valid_percent=round(100 * val / tot, 4),
                     missing_percent=round(100 * (tot - val) / tot, 4), aoi_coverage_percent=round(100 * cov, 4),
                     native_resolution=res, crs=", ".join(sorted(crss)), warnings=list(warnings),
                     checks_passed=["raster readable", "AOI transformed into raster CRS"])
    prov = Provenance(provider="SOILGRIDS", dataset_name="SoilGrids 250 m", dataset_version="2.0", origin=origin,
                      measurement_kind=MeasurementKind.STATISTICAL_SUMMARY, source_files=sorted({l["file"] for l in layers}),
                      units="per layer (see layers: source_units and converted_units)",
                      method="native-pixel window clip masked to the AOI polygon (bbox when only a bbox is given); converted = raw / ISRIC conversion factor",
                      notes=["raw and converted statistics both stored per layer", "values are modelled predictions, not measurements"])
    return SoilResult(layers=layers, quality=q, provenance=prov, warnings=warnings, rasters=rasters)
