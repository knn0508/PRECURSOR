"""Stack manifest: one honest inventory of every dataset in an area's data stack.

Raster layers sit on the common reference grid (an aligned copy exists); series (rainfall, SMAP) and vector datasets
(seismic, cataloged landslides) are listed as non-raster entries. Every kind the system knows is listed: a dataset
that was never processed appears as NOT_RUN with a reason, never as an empty or zero entry. File NAMES only, never paths.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EnvironmentalLayer, EnvironmentalProcessingRun
from app.services.environmental import queries, storage
from app.services.environmental.types import (
    RASTER_KINDS, SERIES_KINDS, TEMPORAL_OF, VECTOR_KINDS, DataOrigin, LayerKind,
)

GOOD = ("PROCESSED", "PARTIALLY_PROCESSED")


def kind_of(layer_type: str) -> str:
    k = LayerKind(layer_type)
    return "series" if k in SERIES_KINDS else "vector" if k in VECTOR_KINDS else "raster" if k in RASTER_KINDS else "raster"


def lineage_hash(layer: EnvironmentalLayer) -> str:
    """Stable fingerprint of WHAT the layer is derived from: provenance + input hash + output checksum."""
    blob = json.dumps({"provenance": layer.provenance, "input_hash": layer.input_hash, "checksum": layer.checksum_sha256,
                       "type": layer.layer_type, "version": layer.dataset_version}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _entry(layer: EnvironmentalLayer) -> dict[str, Any]:
    kind = kind_of(layer.layer_type)
    q = layer.quality or {}
    ok = layer.status in GOOD
    file = Path(layer.aligned_file_path or layer.file_path).name if (layer.aligned_file_path or layer.file_path) else None
    return {
        "layer_id": layer.id, "layer_type": layer.layer_type, "kind": kind,
        "temporal_kind": layer.temporal_kind or TEMPORAL_OF[LayerKind(layer.layer_type)].value, "status": layer.status,
        "units": layer.units, "crs": layer.crs, "native_resolution": layer.native_resolution,
        "processing_resolution": layer.processing_resolution,
        "on_reference_grid": bool(layer.aligned_file_path) if kind == "raster" else False,
        "source": {"provider": layer.source_provider, "dataset_name": layer.dataset_name, "dataset_version": layer.dataset_version},
        "temporal_start": layer.temporal_start, "temporal_end": layer.temporal_end, "data_origin": layer.data_origin,
        "synthetic": layer.data_origin == DataOrigin.SYNTHETIC_FIXTURE.value, "validation_status": layer.validation_status,
        "nodata": layer.nodata,
        "coverage": {"valid_percent": q.get("valid_percent"), "missing_percent": q.get("missing_percent"),
                     "aoi_coverage_percent": q.get("aoi_coverage_percent")},
        "provenance": layer.provenance or {}, "lineage_hash": lineage_hash(layer) if ok else None, "input_hash": layer.input_hash,
        "file": file if ok else None,
        "reason": None if ok else ((layer.statistics or {}).get("reason") or "no input available"),
    }


def _missing_entry(kind: LayerKind) -> dict[str, Any]:
    return {
        "layer_id": None, "layer_type": kind.value, "kind": kind_of(kind.value), "temporal_kind": TEMPORAL_OF[kind].value,
        "status": "NOT_RUN", "units": None, "crs": None, "native_resolution": None, "processing_resolution": None,
        "on_reference_grid": False, "source": {"provider": None, "dataset_name": None, "dataset_version": None},
        "temporal_start": None, "temporal_end": None, "data_origin": None, "synthetic": False, "validation_status": "NOT_VALIDATED",
        "nodata": None, "coverage": {"valid_percent": None, "missing_percent": None, "aoi_coverage_percent": None},
        "provenance": {}, "lineage_hash": None, "input_hash": None, "file": None, "reason": "not processed for this area yet",
    }


def build_manifest(db: Session, area_id: uuid.UUID) -> dict[str, Any]:
    layers = queries.latest_layers(db, area_id)
    present = {LayerKind(x.layer_type) for x in layers}
    entries = [_entry(x) for x in sorted(layers, key=lambda x: (list(LayerKind).index(LayerKind(x.layer_type)), x.dataset_name))]
    entries += [_missing_entry(k) for k in LayerKind if k not in present]
    run = db.scalars(select(EnvironmentalProcessingRun).where(
        EnvironmentalProcessingRun.area_id == area_id, EnvironmentalProcessingRun.reference_grid.is_not(None))
        .order_by(EnvironmentalProcessingRun.created_at.desc())).first()
    counts = {
        "entries": len(entries),
        "raster": sum(e["kind"] == "raster" for e in entries), "series": sum(e["kind"] == "series" for e in entries),
        "vector": sum(e["kind"] == "vector" for e in entries),
        "static": sum(e["temporal_kind"] == "static" for e in entries), "dynamic": sum(e["temporal_kind"] == "dynamic" for e in entries),
        "available": sum(e["status"] in GOOD for e in entries), "not_available": sum(e["status"] not in GOOD for e in entries),
        "on_reference_grid": sum(e["on_reference_grid"] for e in entries), "synthetic": sum(e["synthetic"] for e in entries),
    }
    return {
        "area_id": area_id, "run_id": run.id if run else None, "generated_at": datetime.now(UTC),
        "reference_grid": run.reference_grid if run else None, "entries": entries, "counts": counts,
        "contains_synthetic_data": counts["synthetic"] > 0,
        "validation_status": "NOT_VALIDATED", "real_data_validation": "NOT_PERFORMED",
        "notes": [
            "Inventory of datasets with provenance; availability is not validation.",
            "Raster entries are resampled to the reference grid; resampling does not add information.",
            "Series and vector datasets are listed as non-raster entries. A NOT_RUN or NOT_AVAILABLE entry means no data, not zero.",
            "Nothing in this stack is a landslide risk score, probability or prediction.",
        ],
    }


def write_manifest(data_root: Path, area_id: uuid.UUID, manifest: dict[str, Any]) -> Path:
    from app.services.environmental.pipeline.runs import json_safe  # lazy: runs imports this module

    d = storage.area_dir(data_root, area_id, "features")
    p = d / "manifest.json"
    p.write_text(json.dumps(json_safe(manifest), indent=2), encoding="utf-8")
    return p
