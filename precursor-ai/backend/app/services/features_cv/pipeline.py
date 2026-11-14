"""Feature extraction run: Phase 4 stack -> feature COGs + features manifest.json. Deterministic, no randomness, no ML.

Entry points: `run_extraction` (service/CLI) and `read_features_manifest` (read-only API). Outputs go to
data/processed/features/<area_id>/ only; the Phase 4 files are never modified.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.services.environmental.pipeline.runs import json_safe
from app.services.features_cv import stack as stk
from app.services.features_cv.change import DatedInput
from app.services.features_cv.export import write_cog
from app.services.features_cv.registry import DEFAULT_PARAMS, REGISTRY, ExtractionContext
from app.services.features_cv.tiling import fit_normalisation
from app.services.features_cv.types import (
    CODE_VERSION, FEATURE_SCHEMA_VERSION, FeatureError, NotAvailable, forbidden_names)

MANIFEST_NAME = "manifest.json"


def _stats(a: np.ndarray) -> dict[str, Any]:
    v = a[np.isfinite(a)]
    n = int(a.size)
    return {"valid_percent": round(100.0 * v.size / n, 4) if n else None,
            "min": float(v.min()) if v.size else None, "max": float(v.max()) if v.size else None, "mean": float(v.mean()) if v.size else None}


def _check_params(params: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(params) - set(DEFAULT_PARAMS))
    if unknown:
        raise FeatureError(f"unknown extraction parameter(s): {unknown}")
    return {**DEFAULT_PARAMS, **params}


def run_extraction(data_root: Path, area_id: uuid.UUID, params: dict[str, Any] | None = None, *, normalise: str | None = None,
                   extractors: list[str] | None = None, change_inputs: dict[str, list[DatedInput]] | None = None,
                   now: datetime | None = None) -> dict[str, Any]:
    p = _check_params(params or {})
    if normalise not in (None, "zscore", "minmax"):
        raise FeatureError(f"unknown normalisation {normalise!r}")
    st = stk.load_stack(data_root, area_id)  # NotAvailable if the Phase 4 stack is missing
    by_type = {e["layer_type"]: k for k, e in st.layers.items()}  # first key per layer type
    ctx = ExtractionContext(arrays={lt: st.arrays[k] for lt, k in by_type.items()}, layers={lt: st.layers[k] for lt, k in by_type.items()},
                            grid=st.grid, params=p, change_inputs=change_inputs or {})
    out_dir = stk.features_dir(data_root, area_id)
    features: list[dict[str, Any]] = []
    for name in extractors or REGISTRY.names():
        ex = REGISTRY.get(name)
        results, skipped = ex.extract(ctx)
        for r in results:
            s = r.spec
            if forbidden_names([s.name]):
                raise FeatureError(f"feature name {s.name!r} looks like a score/prediction")
            tags = {"feature": s.name, "units": s.units, "schema_version": FEATURE_SCHEMA_VERSION, "code_version": CODE_VERSION,
                    "synthetic_inputs": "1" if st.contains_synthetic else "0"}
            f = write_cog(out_dir / "rasters" / f"{s.name}.tif", r.array, r.transform, st.grid["crs"], tags)
            entry: dict[str, Any] = {**s.to_dict(), "status": "DONE", "file": f.name, "grid": "reference" if r.on_reference_grid else "block",
                                     "resolution_m": st.grid["resolution_m"] * (1 if r.on_reference_grid else int(s.parameters.get("stride_px", 1))),
                                     "shape": list(r.array.shape), "transform": list(tuple(r.transform)[:6]), **_stats(r.array),
                                     "array_sha256": hashlib.sha256(np.ascontiguousarray(r.array).tobytes()).hexdigest(), "notes": r.notes, "details": r.extra,
                                     "source_synthetic": any(ctx.layers.get(l, {}).get("synthetic") for l in s.source_layers)}
            if normalise and np.isfinite(r.array).any():
                try:
                    entry["normalisation"] = fit_normalisation(r.array, normalise).to_dict()
                except FeatureError as exc:
                    entry["normalisation"] = {"status": "NOT_AVAILABLE", "reason": str(exc)}
            features.append(entry)
        for sk in skipped:
            features.append({"name": sk["feature"], "status": sk["status"], "reason": sk["reason"]})
    done = [f for f in features if f["status"] == "DONE"]
    manifest: dict[str, Any] = {
        "schema": "features_cv.features_manifest", "feature_schema_version": FEATURE_SCHEMA_VERSION, "code_version": CODE_VERSION,
        "generated_at": (now or datetime.now(UTC)).isoformat(), "area_id": str(area_id),
        "source": {"phase4_manifest_sha256": st.manifest_sha256, "phase4_run_id": st.manifest.get("run_id")},
        "grid": {**st.grid, "bounds": (st.manifest.get("reference_grid") or {}).get("bounds")},
        "parameters": json_safe({**p, "normalise": normalise}), "seed": None, "randomness": "none (deterministic)",
        "contains_synthetic_data": st.contains_synthetic or any(f.get("source_synthetic") for f in done),
        "input_layers": [{"key": k, "layer_type": e["layer_type"], "synthetic": e.get("synthetic"), "data_origin": e.get("data_origin"),
                          "lineage_hash": e.get("lineage_hash"), "temporal_kind": e.get("temporal_kind"), "units": e.get("units"), "file": e.get("file")}
                         for k, e in st.layers.items()],
        "skipped_layers": st.skipped, "features": features,
        "counts": {"done": len(done), "not_available": len(features) - len(done)},
        "validation_status": "NOT_VALIDATED", "real_data_validation": "NOT_PERFORMED",
        "notes": ["Descriptive rasters derived from the Phase 4 aligned stack; availability is not validation.",
                  "Missing is NaN, never zero. Texture features live on a coarser block grid (see each feature's grid and resolution_m).",
                  "Nothing in this output is a landslide risk score, probability, class or prediction."],
    }
    (out_dir / MANIFEST_NAME).write_text(json.dumps(json_safe(manifest), indent=2), encoding="utf-8")
    return manifest


def read_features_manifest(data_root: Path, area_id: uuid.UUID) -> dict[str, Any]:
    p = data_root / "processed" / "features" / str(area_id) / MANIFEST_NAME  # no mkdir on a read path
    if not p.exists():
        raise NotAvailable("no feature extraction has been run for this area")
    return stk.read_json(p)
