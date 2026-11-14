"""Read-side helpers for the environmental API. They turn stored rows into the Pydantic contracts and never invent data:
a missing layer is `available=False` with a reason, a missing observation is null."""
from __future__ import annotations

import uuid
from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EnvironmentalFeature, EnvironmentalLayer, EnvironmentalProcessingRun
from app.schemas.environmental import CoverageItem, CoverageRead, FeatureRead, LayerRead, RainfallPoint, RainfallRead
from app.services.environmental.types import FEATURE_GROUPS, RASTER_KINDS, DataOrigin, LayerKind

LABELS = {
    DataOrigin.SYNTHETIC_FIXTURE.value: "SYNTHETIC TEST DATA: not a real observation",
    DataOrigin.REAL_SATELLITE.value: "Source data from a registered download; NOT scientifically validated",
    DataOrigin.LOCAL_UNVERIFIED.value: "Local file of unverified provenance; NOT scientifically validated",
}
# What "coverage" lists. INSAR is one row (any of the three products).
COVERAGE_ROWS = ["ELEVATION", "SLOPE", "ASPECT", "RAINFALL", "SMAP_SOIL_MOISTURE", "SOIL", "LAND_COVER", "LITHOLOGY", "NDVI",
                 "DISTANCE_RIVER", "DISTANCE_FAULT", "DISTANCE_ROAD", "HISTORICAL_LANDSLIDES", "SEISMIC", "INSAR"]
INSAR_KINDS = {LayerKind.INSAR_DISPLACEMENT.value, LayerKind.INSAR_COHERENCE.value, LayerKind.INSAR_VELOCITY.value}
GROUP_LAYERS = {"terrain": ["ELEVATION", "SLOPE", "ASPECT"], "rainfall": ["RAINFALL"], "smap": ["SMAP_SOIL_MOISTURE"], "soil": ["SOIL"], "land_cover": ["LAND_COVER"],
                "lithology": ["LITHOLOGY"], "vegetation": ["NDVI"], "distances": ["DISTANCE_RIVER", "DISTANCE_FAULT", "DISTANCE_ROAD"],
                "historical_landslides": ["HISTORICAL_LANDSLIDES"], "seismic": ["SEISMIC"], "insar": sorted(INSAR_KINDS)}


def layer_read(layer: EnvironmentalLayer) -> LayerRead:
    fp = mapping(to_shape(layer.footprint)) if layer.footprint is not None else None
    stats = {k: v for k, v in (layer.statistics or {}).items() if k not in ("series",)}  # series served by /rainfall
    return LayerRead.model_validate(layer).model_copy(update={
        "footprint": fp, "statistics": stats,
        "label": "No data available for this layer (this is not a zero value)" if layer.status == "NOT_AVAILABLE" else LABELS.get(layer.data_origin, ""),
        "aligned": bool(layer.aligned_file_path),
        "has_raster": bool(layer.file_path) and layer.layer_type in {k.value for k in RASTER_KINDS} and not layer.layer_type.startswith("INSAR"),
    })


def latest_layers(db: Session, area_id: uuid.UUID) -> list[EnvironmentalLayer]:
    """Newest layer per layer_type that has data (PROCESSED/PARTIALLY_PROCESSED), else the newest status row."""
    rows = list(db.scalars(select(EnvironmentalLayer).where(EnvironmentalLayer.area_id == area_id)
                           .order_by(EnvironmentalLayer.created_at.desc())))
    best: dict[tuple[str, str], EnvironmentalLayer] = {}
    for r in rows:
        key = (r.layer_type, r.dataset_name)  # several soil properties / depths are separate layers
        cur = best.get(key)
        has_data = r.status in ("PROCESSED", "PARTIALLY_PROCESSED")
        if cur is None or (has_data and cur.status not in ("PROCESSED", "PARTIALLY_PROCESSED")):
            best[key] = r
    return list(best.values())


def coverage(db: Session, area_id: uuid.UUID) -> CoverageRead:
    layers = latest_layers(db, area_id)
    by_type: dict[str, list[EnvironmentalLayer]] = {}
    for layer in layers:
        by_type.setdefault("INSAR" if layer.layer_type in INSAR_KINDS else layer.layer_type, []).append(layer)
    items: list[CoverageItem] = []
    for row in COVERAGE_ROWS:
        ls = by_type.get(row)
        if not ls:
            items.append(CoverageItem(layer_type=row, available=False, status="NOT_RUN", reason="not processed for this area yet"))
            continue
        layer = ls[0]
        q = layer.quality or {}
        ok = layer.status in ("PROCESSED", "PARTIALLY_PROCESSED")
        items.append(CoverageItem(
            layer_type=row, available=ok, status=layer.status, data_origin=layer.data_origin,
            valid_percent=q.get("valid_percent"), missing_percent=q.get("missing_percent"),
            aoi_coverage_percent=q.get("aoi_coverage_percent"), temporal_start=layer.temporal_start,
            temporal_end=layer.temporal_end, layer_id=layer.id,
            reason=None if ok else ((layer.statistics or {}).get("reason") or "no input available"),
        ))
    last = db.scalar(select(EnvironmentalProcessingRun.completed_at).where(
        EnvironmentalProcessingRun.area_id == area_id, EnvironmentalProcessingRun.completed_at.is_not(None))
        .order_by(EnvironmentalProcessingRun.completed_at.desc()).limit(1))
    return CoverageRead(area_id=area_id, items=items, missing_datasets=[i.layer_type for i in items if not i.available],
                        last_processed_at=last)


def feature_read(row: EnvironmentalFeature | None, group: str) -> FeatureRead:
    if row is None:
        return FeatureRead(group=group, status="NOT_AVAILABLE", values={}, units={}, lineage=[],
                           measurement_kind="STATISTICAL_SUMMARY", data_origin="NONE", warnings=["not processed for this area yet"],
                           label="No data. This is not a zero value.")
    return FeatureRead(group=group, status=row.status, values=row.values, units=row.units, lineage=row.lineage,
                       measurement_kind=row.measurement_kind, data_origin=row.data_origin, warnings=row.warnings,
                       label=LABELS.get(row.data_origin, ""))


def latest_features(db: Session, area_id: uuid.UUID) -> tuple[uuid.UUID | None, dict[str, EnvironmentalFeature]]:
    out: dict[str, EnvironmentalFeature] = {}
    rows = db.scalars(select(EnvironmentalFeature).where(EnvironmentalFeature.area_id == area_id)
                      .order_by(EnvironmentalFeature.created_at.desc()))
    for r in rows:
        cur = out.get(r.feature_group)
        if cur is None or (r.status in ("PROCESSED", "PARTIALLY_PROCESSED") and cur.status not in ("PROCESSED", "PARTIALLY_PROCESSED")):
            out[r.feature_group] = r
    run_id = max(out.values(), key=lambda r: r.created_at).run_id if out else None
    return run_id, out


def rainfall_read(db: Session, area_id: uuid.UUID) -> RainfallRead:
    layer = next((layer for layer in latest_layers(db, area_id) if layer.layer_type == "RAINFALL"), None)
    if layer is None or layer.status not in ("PROCESSED", "PARTIALLY_PROCESSED"):
        reason = ((layer.statistics or {}).get("reason") if layer else None) or "no rainfall processed for this area"
        return RainfallRead(area_id=area_id, status=layer.status if layer else "NOT_RUN", data_origin=layer.data_origin if layer else None,
                            source=None, temporal_start=None, temporal_end=None, daily=[], monthly=[], rolling={},
                            observed_days=0, missing_days=0, notes=[reason])
    s = layer.statistics or {}
    pts = lambda seq: [RainfallPoint(date=p["date"], precipitation_mm=p.get("precipitation_mm"), observed=bool(p.get("observed"))) for p in (seq or [])]  # noqa: E731
    return RainfallRead(
        area_id=area_id, status=layer.status, data_origin=layer.data_origin, source=f"{layer.dataset_name} {layer.dataset_version or ''}".strip(),
        temporal_start=layer.temporal_start, temporal_end=layer.temporal_end, daily=pts(s.get("daily")), monthly=pts(s.get("monthly")),
        rolling={k: pts(v) for k, v in (s.get("rolling") or {}).items()}, observed_days=int(s.get("observed_days", 0)),
        missing_days=int(s.get("missing_days", 0)), notes=list(s.get("notes") or []) + [LABELS.get(layer.data_origin, "")],
    )


def groups_in_order() -> tuple[str, ...]:
    return FEATURE_GROUPS


def feature_group_payload(rows: dict[str, EnvironmentalFeature]) -> list[FeatureRead]:
    return [feature_read(rows.get(g), g) for g in FEATURE_GROUPS]


def _unused(_: Any) -> None:  # pragma: no cover
    return None
