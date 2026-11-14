"""Dataset run: Phase 4 stack (+ Phase 5 feature rasters) + catalog events -> samples.parquet, excluded.json, manifest.json.

Files only (no DB table). Per-point dynamic features are NOT computed here (deferred to Phase 6). The events loader that
reads the Phase 2 catalog from PostgreSQL lives in `events.py`; this module takes plain dicts so it stays testable.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from affine import Affine

from app.services.environmental.dem.slope import slope_degrees
from app.services.environmental.pipeline.runs import json_safe
from app.services.environmental.raster.io import read_float
from app.services.features_cv import dataset as ds
from app.services.features_cv import stack as stk
from app.services.features_cv.export import to_parquet
from app.services.features_cv.pipeline import MANIFEST_NAME as FEATURES_MANIFEST
from app.services.features_cv.types import (
    CODE_VERSION, DATASET_SCHEMA_VERSION, FEATURE_SCHEMA_VERSION, SYNTHETIC_ORIGIN, FeatureError, NotAvailable)

EVENTS_ORIGINS = ("REAL_CATALOG", SYNTHETIC_ORIGIN, "UNKNOWN")
DYNAMIC_LAYERS = ("INSAR_DISPLACEMENT", "INSAR_COHERENCE", "INSAR_VELOCITY")


def _static_arrays(data_root: Path, area_id: uuid.UUID, st: stk.Stack) -> tuple[dict[str, np.ndarray], list[dict[str, str]], str | None]:
    arrays, notes = {}, []
    for k, a in st.arrays.items():
        if st.layers[k]["layer_type"] in DYNAMIC_LAYERS:
            notes.append({"layer": k, "reason": "dynamic InSAR layer: per-point dynamic features are deferred to Phase 6"})
            continue
        arrays[k] = a
    fm_path = data_root / "processed" / "features" / str(area_id) / FEATURES_MANIFEST
    fm_sha = None
    if fm_path.exists():
        fm_sha = stk.sha256_file(fm_path)
        fdir = fm_path.parent / "rasters"
        for f in stk.read_json(fm_path).get("features", []):
            if f.get("status") != "DONE":
                continue
            if f.get("grid") != "reference":
                notes.append({"layer": f["name"], "reason": "block-grid feature: not sampled per point in dataset schema 1.0.0"})
                continue
            p = (fdir / Path(f["file"]).name).resolve()
            if not p.is_relative_to(fdir.resolve()) or not p.exists():
                notes.append({"layer": f["name"], "reason": "feature raster file missing"})
                continue
            arr, meta = read_float(p)
            if (meta.width, meta.height) != (st.grid["width"], st.grid["height"]):
                raise FeatureError(f"feature raster {f['name']} is not on the reference grid")
            arrays[f["name"]] = arr
    return arrays, notes, fm_sha


def run_dataset(data_root: Path, area_id: uuid.UUID, events: list[dict[str, Any]], params: ds.DatasetParams | None = None, *,
                events_origin: str = "UNKNOWN", now: datetime | None = None) -> dict[str, Any]:
    if events_origin not in EVENTS_ORIGINS:
        raise FeatureError(f"events_origin must be one of {EVENTS_ORIGINS}")
    p = params or ds.DatasetParams()
    st = stk.load_stack(data_root, area_id)
    static, dyn_notes, fm_sha = _static_arrays(data_root, area_id, st)
    if "SLOPE" in st.arrays:
        strat, strat_src = st.arrays["SLOPE"], "SLOPE layer"
    elif "ELEVATION" in st.arrays:
        strat, strat_src = slope_degrees(st.arrays["ELEVATION"], st.grid["crs"], Affine(*st.grid["transform"][:6])), "slope derived from ELEVATION (Horn)"
    else:
        raise NotAvailable("dataset needs a SLOPE or ELEVATION layer on the reference grid (valid-pixel mask and terrain strata)")
    valid = np.isfinite(strat)
    res = ds.build_samples(events, st.grid, static, strat, valid, p)
    out = stk.datasets_dir(data_root, area_id)
    to_parquet(res.samples, out / "samples.parquet")
    (out / "excluded.json").write_text(json.dumps(json_safe(res.excluded), indent=2), encoding="utf-8")
    synthetic = st.contains_synthetic or events_origin == SYNTHETIC_ORIGIN
    manifest: dict[str, Any] = {
        "schema": "features_cv.dataset_manifest", "dataset_schema_version": DATASET_SCHEMA_VERSION, "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "code_version": CODE_VERSION, "generated_at": (now or datetime.now(UTC)).isoformat(), "area_id": str(area_id),
        "source": {"phase4_manifest_sha256": st.manifest_sha256, "features_manifest_sha256": fm_sha, "events_origin": events_origin},
        "grid": st.grid, "parameters": json_safe({**p.__dict__, "stratification_source": strat_src, "valid_mask": "finite stratification raster"}),
        "seed": p.seed, "contains_synthetic_data": synthetic,
        "files": {"samples": "samples.parquet", "excluded": "excluded.json"}, **json_safe(res.info),
        "not_sampled_layers": dyn_notes, "skipped_layers": st.skipped, "caveats": ds.CAVEATS, "warnings": res.warnings,
        "validation_status": "NOT_VALIDATED", "real_data_validation": "NOT_PERFORMED",
        "notes": ["A data product for a future model: no training, scoring or prediction happens here."],
    }
    (out / "manifest.json").write_text(json.dumps(json_safe(manifest), indent=2), encoding="utf-8")
    return manifest


def read_dataset_summary(data_root: Path, area_id: uuid.UUID) -> dict[str, Any]:
    p = data_root / "processed" / "datasets" / str(area_id) / "manifest.json"  # no mkdir on a read path
    if not p.exists():
        raise NotAvailable("no labelled dataset has been built for this area")
    m = stk.read_json(p)
    keys = ("dataset_schema_version", "feature_schema_version", "code_version", "generated_at", "area_id", "seed", "contains_synthetic_data", "counts",
            "class_balance", "split", "leakage", "lead_time_anchors_days", "dynamic_columns", "caveats", "warnings", "validation_status", "real_data_validation")
    return {k: m.get(k) for k in keys}
