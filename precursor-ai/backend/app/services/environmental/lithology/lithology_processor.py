"""User-provided lithology/geology (categorical raster or GeoJSON polygons) -> uint16 class raster on the metric target grid.

The legend (class names, colours, citation) comes ONLY from the user's `<stem>.legend.json` sidecar. Without it class ids are
kept, named "class N" and a warning says names are unknown. Nothing here invents lithology names, hardness, erodibility or
risk. Rasters are resampled with NEAREST only, so no class id that is not in the source can appear.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401  (must precede geo libraries)

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from affine import Affine
from rasterio.features import rasterize

from app.services.environmental.external_inputs import (
    aoi_mask, aoi_quality, input_hash, origin_of, raster_is_synthetic, read_geojson, require_metric_grid, to_grid_crs,
    write_class_geotiff, RASTER_SUFFIXES, VECTOR_SUFFIXES,
)
from app.services.environmental.raster.alignment import TargetGrid, align_array
from app.services.environmental.raster.io import inspect_raster, read_float
from app.services.environmental.types import (
    SYNTHETIC_TAG, EnvError, LayerKind, LayerQuality, LayerStatus, MeasurementKind, NotAvailable, Provenance,
)

NODATA = 65535


@dataclass
class LithologyResult:
    path: Path
    quality: LayerQuality
    provenance: Provenance
    stats: dict[str, Any]
    status: LayerStatus
    warnings: list[str]
    input_hash: str
    classes: list[dict[str, Any]] = field(default_factory=list)  # id, name, color, pixels, percent (of valid AOI pixels)
    unknown_classes: list[dict[str, Any]] = field(default_factory=list)  # ids present but absent from the user legend
    legend: dict[str, Any] = field(default_factory=dict)  # legend actually applied (incl. attribute->id mapping for vectors)


def load_legend(path: Path) -> dict[str, Any] | None:
    side = path.with_name(path.stem + ".legend.json")
    if not side.is_file():
        return None
    try:
        doc = json.loads(side.read_text(encoding="utf-8"))
        classes = {}
        for c in doc.get("classes", []):
            i = c["id"]
            if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < NODATA or not isinstance(c["name"], str):
                raise ValueError(f"bad class entry {c!r}")
            if i in classes:
                raise ValueError(f"duplicate class id {i}")
            classes[i] = {"name": c["name"], "color": c.get("color")}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise EnvError(f"{side.name}: invalid legend sidecar ({exc})") from exc
    return {"classes": classes, "attribute": doc.get("attribute"), "source": doc.get("source"), "file": side.name}


def _vector_ids(path: Path, legend: dict | None, attribute: str | None, grid: TargetGrid, warns: list[str]) -> tuple[np.ndarray, dict[int, str]]:
    attr = attribute or (legend or {}).get("attribute")
    if not attr:
        raise EnvError(f"{path.name}: vector lithology needs the class attribute name in the legend sidecar ('attribute') or the attribute= option")
    geoms, props, crs, _ = read_geojson(path)
    by_name = {v["name"]: k for k, v in (legend or {}).get("classes", {}).items()}
    known = set((legend or {}).get("classes", {}))
    rows: list[tuple[Any, Any]] = []  # (geometry in grid crs, raw attribute value)
    skipped = 0
    for g, p in zip(geoms, props):
        if g is None or g.is_empty or not g.is_valid or g.geom_type not in ("Polygon", "MultiPolygon") or p.get(attr) in (None, ""):
            skipped += 1
            continue
        rows.append((to_grid_crs(g, crs, grid), p[attr]))
    if skipped:
        warns.append(f"{path.name}: {skipped} feature(s) skipped (empty/invalid/non-polygon geometry or missing '{attr}')")
    if not rows:
        raise NotAvailable(f"{path.name}: no usable polygon with attribute '{attr}'")
    mapping: dict[Any, int] = {}
    for v in {r[1] for r in rows}:
        if v in by_name:
            mapping[v] = by_name[v]
        elif isinstance(v, int) and not isinstance(v, bool) and v in known:
            mapping[v] = v
    unmatched = sorted((r[1] for r in rows if r[1] not in mapping), key=str)
    unmatched = sorted(set(unmatched), key=str)
    nxt = max(known | set(mapping.values()) | {0}) + 1
    names = {}
    for v in unmatched:
        mapping[v] = nxt
        names[nxt] = str(v)  # the user's own attribute value, not an invented name
        nxt += 1
    if unmatched:
        warns.append(f"{path.name}: {len(unmatched)} attribute value(s) not in the legend got stable ids from sorted values: "
                     f"{ {str(v): mapping[v] for v in unmatched} }")
    arr = rasterize([(g, mapping[v]) for g, v in rows], out_shape=(grid.height, grid.width), transform=grid.transform,
                    fill=NODATA, dtype="uint16", all_touched=False).astype(np.float32)
    arr[arr == NODATA] = np.nan  # later polygons overwrite earlier ones where they overlap
    return arr, names


def process_lithology(files: list[Path], aoi: Any, grid: TargetGrid, out_dir: Path, *, attribute: str | None = None) -> LithologyResult:
    require_metric_grid(grid)
    files = sorted(Path(f) for f in files)
    if not files:
        raise NotAvailable("no lithology input covers the AOI")
    inside, warns = aoi_mask(aoi, grid)
    acc = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
    classes: dict[int, dict] = {}
    sources: list[str] = []
    used: list[str] = []
    native: dict | None = None
    synthetic = False
    has_legend = False
    for f in files:
        suf = f.suffix.lower()
        legend = load_legend(f)
        extra_names: dict[int, str] = {}
        if suf in RASTER_SUFFIXES:
            arr, meta = read_float(f)
            fin = arr[np.isfinite(arr)]
            if fin.size and (not np.all(fin == np.round(fin)) or fin.min() < 0):
                raise EnvError(f"{f.name}: lithology raster must hold non-negative integer class ids")
            if meta.nodata is None:
                warns.append(f"{f.name}: no nodata declared; no pixel treated as missing")
            if meta.crs is None:
                raise EnvError(f"{f.name}: CRS missing; refusing to guess one")
            res = align_array(arr, Affine(*meta.transform), meta.crs, meta.resolution(), grid, LayerKind.LITHOLOGY)
            new, native = res.array, meta.resolution()
            synthetic |= meta.is_synthetic or raster_is_synthetic(f)
        elif suf in VECTOR_SUFFIXES:
            new, extra_names = _vector_ids(f, legend, attribute, grid, warns)
            synthetic |= read_geojson(f)[3]
        else:
            raise EnvError(f"{f.name}: unsupported lithology input; use a GeoTIFF or GeoJSON (Shapefile/GeoPackage unsupported)")
        acc = np.where(np.isnan(acc), new, acc)
        used.append(f.name)
        if legend:
            has_legend = True
            used.append(legend["file"])
            if legend["source"]:
                sources.append(str(legend["source"]))
            for i, c in legend["classes"].items():
                if i in classes and classes[i]["name"] != c["name"]:
                    raise EnvError(f"class id {i} has conflicting names across legends ({classes[i]['name']!r} vs {c['name']!r})")
                classes[i] = c
        for i, n in extra_names.items():
            classes.setdefault(i, {"name": n, "color": None})
    if not np.isfinite(acc[inside]).any():
        raise NotAvailable("lithology input does not provide any valid pixel inside the AOI (valid 0%); nothing written")
    if not has_legend:
        warns.append("no <stem>.legend.json sidecar: class ids kept, names unknown ('class N'); lithology names are NOT inferred")
    vals, cnt = np.unique(acc[inside & np.isfinite(acc)].astype(np.int64), return_counts=True)
    nvalid = int(cnt.sum())
    out_classes, unknown = [], []
    for i, k in zip(vals.tolist(), cnt.tolist()):
        row = {"class_id": i, "pixels": k, "percent": round(100.0 * k / nvalid, 6)}
        if i in classes:
            out_classes.append({**row, "name": classes[i]["name"], "color": classes[i]["color"]})
        elif not has_legend:
            out_classes.append({**row, "name": f"class {i}", "color": None})
        else:
            unknown.append(row)
    if unknown:
        warns.append(f"class ids not in the user legend: {[u['class_id'] for u in unknown]}")
    out_dir = Path(out_dir)
    tags = {"units": "class id", "source": ";".join(used), "resampling": "nearest (rasters); polygon rasterisation (vectors)",
            "legend_source": "; ".join(sources) or "UNKNOWN"}
    if synthetic:
        tags[SYNTHETIC_TAG] = "1"
    path = write_class_geotiff(out_dir / "lithology.tif", acc, grid.transform, grid.crs, tags, NODATA)
    q = aoi_quality(acc, inside, grid, native, passed=["class ids integer", "nearest/rasterised only", "metric grid"], failed=[], warnings=warns)
    legend_out = {"classes": [{"id": i, **c} for i, c in sorted(classes.items())], "source": "; ".join(sources) or None,
                  "legend_present": has_legend}
    stats = {"valid_percent": q.valid_percent, "n_classes": len(out_classes), "n_unknown_classes": len(unknown),
             "class_distribution_percent": {str(c["class_id"]): c["percent"] for c in out_classes}, "crs": grid.crs}
    prov = Provenance(provider="USER_LITHOLOGY", dataset_name="user-provided lithology/geology", origin=origin_of(synthetic),
                      measurement_kind=MeasurementKind.SOURCE_OBSERVATION, source_files=used, units="class id", nodata=float(NODATA),
                      method="categorical raster nearest-neighbour onto grid, or GeoJSON polygon rasterisation at pixel centres",
                      notes=["classes and names are as supplied by the user; no hardness/erodibility interpretation"])
    status = LayerStatus.PROCESSED if q.valid_percent == 100.0 and not unknown else LayerStatus.PARTIALLY_PROCESSED
    return LithologyResult(path, q, prov, stats, status, warns, input_hash(files, grid, aoi, {"attribute": attribute}),
                           out_classes, unknown, legend_out)
