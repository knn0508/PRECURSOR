"""/api/v1/environmental: processed environmental layers, features and quality for monitored areas.

Never downloads source datasets and never exposes a filesystem path. The ONE outbound call is the explicit
`POST /areas/{id}/seismic/refresh` (anonymous, read-only USGS query, small JSON). Environmental measurements are not
landslide risk: nothing here returns a score, probability or prediction.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, time
from functools import lru_cache

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import FileResponse
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, mapping
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError, UpstreamError
from app.database.session import SessionLocal, get_db
from app.models import EarthquakeEvent, EnvironmentalLayer, EnvironmentalProcessingRun, LandslideEvent, MonitoredArea
from app.schemas.environmental import (
    CoverageRead, DatasetList, EventsRead, FeatureRead, FeaturesRead, LayerList, LayerRead, LegendClass, LegendRead, ManifestRead,
    ProcessConfig, QualityReportRead, RainfallRead, RunCreateResponse, RunList, RunRead, RunSummary, SeismicRefreshRequest,
    SeismicRefreshResponse,
)
from app.services.environmental import manifest as manifest_mod
from app.services.environmental import preview, queries, storage
from app.services.environmental.catalog import DATASETS
from app.services.environmental.pipeline.runs import EnvironmentalRunService, json_safe
from app.services.environmental.providers.usgs_earthquake import USGSEarthquakeProvider
from app.services.environmental.types import EnvError, LayerKind, NotAvailable

router = APIRouter(prefix="/environmental", tags=["environmental"])

HIST_LIMITS = [
    "Cataloged historical events only: the NASA Global Landslide Catalog is a one-time export whose last event is dated 2017-09-28.",
    "Incomplete, reporting-biased and not ground truth; absence of an event proves nothing.",
]
SEISMIC_LIMITS = [
    "Independent earthquake observations from the USGS catalog. No causal link to any landslide is implied.",
    "No seismic risk score is computed.",
]


@lru_cache
def get_env_service() -> EnvironmentalRunService:
    return EnvironmentalRunService(SessionLocal, get_settings())


def get_usgs() -> USGSEarthquakeProvider:
    return USGSEarthquakeProvider()


def _area(db: Session, area_id: uuid.UUID) -> MonitoredArea:
    a = db.get(MonitoredArea, area_id)
    if a is None:
        raise NotFoundError(f"Monitored area {area_id} not found")
    return a


def _run(db: Session, run_id: uuid.UUID) -> EnvironmentalProcessingRun:
    r = db.get(EnvironmentalProcessingRun, run_id, populate_existing=True)
    if r is None:
        raise NotFoundError(f"Processing run {run_id} not found")
    return r


# ---- catalog / layers ------------------------------------------------------------------------------
@router.get("/datasets", response_model=DatasetList, summary="Datasets Phase 4 knows, with honest implementation status")
def list_datasets() -> DatasetList:
    return DatasetList(items=DATASETS)


@router.get("/layers", response_model=LayerList)
def list_layers(layer_type: str | None = None, area_id: uuid.UUID | None = None, offset: int = Query(0, ge=0),
                limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)) -> LayerList:
    q, cq = select(EnvironmentalLayer), select(func.count()).select_from(EnvironmentalLayer)
    for cond in ([EnvironmentalLayer.layer_type == layer_type] if layer_type else []) + ([EnvironmentalLayer.area_id == area_id] if area_id else []):
        q, cq = q.where(cond), cq.where(cond)
    rows = db.scalars(q.order_by(EnvironmentalLayer.created_at.desc()).offset(offset).limit(limit)).all()
    return LayerList(items=[queries.layer_read(r) for r in rows], total=db.scalar(cq) or 0)


@router.get("/areas/{area_id}/layers", response_model=LayerList, summary="Newest layer per type for the area")
def area_layers(area_id: uuid.UUID, db: Session = Depends(get_db)) -> LayerList:
    _area(db, area_id)
    rows = queries.latest_layers(db, area_id)
    return LayerList(items=[queries.layer_read(r) for r in rows], total=len(rows))


@router.get("/areas/{area_id}/coverage", response_model=CoverageRead)
def area_coverage(area_id: uuid.UUID, db: Session = Depends(get_db)) -> CoverageRead:
    _area(db, area_id)
    return queries.coverage(db, area_id)


def _layer(db: Session, layer_id: uuid.UUID) -> EnvironmentalLayer:
    lay = db.get(EnvironmentalLayer, layer_id)
    if lay is None:
        raise NotFoundError(f"Layer {layer_id} not found")
    return lay


def _raster_file(lay: EnvironmentalLayer, settings: Settings):
    if not lay.file_path or lay.layer_type.startswith("INSAR"):
        raise NotFoundError("this layer has no raster served here (InSAR products are served by /api/v1/insar)")
    try:
        f = storage.resolve_output(settings.data_root, lay.file_path)
    except ValueError:
        raise NotFoundError("raster not available") from None
    if not f.is_file():
        raise NotFoundError("raster file is missing on disk")
    return f


@router.get("/layers/{layer_id}/raster", summary="The registered GeoTIFF, by id only")
def layer_raster(layer_id: uuid.UUID, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> FileResponse:
    lay = _layer(db, layer_id)
    return FileResponse(_raster_file(lay, settings), media_type="image/tiff", filename=f"{lay.layer_type.lower()}_{lay.id}.tif",
                        headers={"X-Data-Origin": lay.data_origin, "X-Units": lay.units or ""})


def _classes(lay: EnvironmentalLayer) -> list[dict]:
    legend = (lay.statistics or {}).get("legend")
    if legend:
        return legend
    ids = [c.get("class_id", c.get("id")) for c in (lay.statistics or {}).get("classes", [])]
    return preview.default_class_colors(ids)


@router.get("/layers/{layer_id}/legend", response_model=LegendRead)
def layer_legend(layer_id: uuid.UUID, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> LegendRead:
    lay = _layer(db, layer_id)
    kind = preview.scale_kind(lay.layer_type)
    base = dict(layer_id=lay.id, layer_type=lay.layer_type, units=lay.units, kind=kind)
    if kind == "categorical":
        return LegendRead(**base, classes=[LegendClass(**c) for c in _classes(lay)],
                          note="Official class legend preserved; classes are not risk labels.")
    if kind == "circular":
        return LegendRead(**base, vmin=0, vmax=360, colors=[],
                          note="Aspect: downslope direction in degrees clockwise from north on a circular hue wheel; flat cells are no-data.")
    vmin, vmax = (None, None)
    try:
        vmin, vmax = preview.value_range(_raster_file(lay, settings), lay.layer_type)
    except NotFoundError:
        pass
    return LegendRead(**base, vmin=vmin, vmax=vmax, colors=preview.RAMP_HEX, note="Scale is the 2nd-98th percentile of valid pixels; nodata is transparent, never zero.")


@router.get("/layers/{layer_id}/preview", summary="Quick-look PNG (nodata transparent)")
def layer_preview(layer_id: uuid.UUID, vmin: float | None = None, vmax: float | None = None, db: Session = Depends(get_db),
                  settings: Settings = Depends(get_settings)) -> Response:
    lay = _layer(db, layer_id)
    f = _raster_file(lay, settings)
    if preview.scale_kind(lay.layer_type) == "continuous" and (vmin is None or vmax is None):
        a, b = preview.value_range(f, lay.layer_type)
        vmin, vmax = (a if vmin is None else vmin), (b if vmax is None else vmax)
    png = preview.render_png(f, lay.layer_type, vmin=vmin, vmax=vmax, classes=_classes(lay) if lay.layer_type in (LayerKind.LAND_COVER.value, LayerKind.LITHOLOGY.value) else None)
    return Response(png, media_type="image/png", headers={"X-Data-Origin": lay.data_origin, "X-Units": lay.units or "",
                                                          "X-Scale": f"vmin={vmin};vmax={vmax}"})


# ---- processing ------------------------------------------------------------------------------------
@router.post("/areas/{area_id}/process", response_model=RunCreateResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="Queue a pipeline run for the area (uses data that is already on disk or in the database)")
def process_area(area_id: uuid.UUID, body: ProcessConfig | None = None, db: Session = Depends(get_db),
                 svc: EnvironmentalRunService = Depends(get_env_service)) -> RunCreateResponse:
    run = svc.create_run(db, area_id, body or ProcessConfig())
    svc.submit(run.id)
    db.refresh(run)
    return RunCreateResponse(run=RunSummary.model_validate(run))


@router.get("/processing-runs", response_model=RunList)
def list_runs(area_id: uuid.UUID | None = None, status_: str | None = Query(None, alias="status"), offset: int = Query(0, ge=0),
              limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)) -> RunList:
    q, cq = select(EnvironmentalProcessingRun), select(func.count()).select_from(EnvironmentalProcessingRun)
    for cond in ([EnvironmentalProcessingRun.area_id == area_id] if area_id else []) + ([EnvironmentalProcessingRun.status == status_] if status_ else []):
        q, cq = q.where(cond), cq.where(cond)
    rows = db.scalars(q.order_by(EnvironmentalProcessingRun.created_at.desc()).offset(offset).limit(limit)).all()
    return RunList(items=[RunSummary.model_validate(r) for r in rows], total=db.scalar(cq) or 0)


@router.get("/processing-runs/{run_id}", response_model=RunRead)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db)) -> RunRead:
    r = _run(db, run_id)
    return RunRead(**RunSummary.model_validate(r).model_dump(), stages=r.stages, config=r.config, warnings=r.warnings)


@router.post("/processing-runs/{run_id}/cancel", response_model=RunSummary)
def cancel_run(run_id: uuid.UUID, db: Session = Depends(get_db), svc: EnvironmentalRunService = Depends(get_env_service)):
    return RunSummary.model_validate(svc.cancel(db, run_id))


# ---- features and per-topic views --------------------------------------------------------------------
def _group(db: Session, area_id: uuid.UUID, group: str) -> FeatureRead:
    _area(db, area_id)
    _, rows = queries.latest_features(db, area_id)
    return queries.feature_read(rows.get(group), group)


@router.get("/areas/{area_id}/features", response_model=FeaturesRead)
def area_features(area_id: uuid.UUID, db: Session = Depends(get_db)) -> FeaturesRead:
    _area(db, area_id)
    run_id, rows = queries.latest_features(db, area_id)
    return FeaturesRead(area_id=area_id, run_id=run_id, groups=queries.feature_group_payload(rows))


@router.get("/areas/{area_id}/terrain", response_model=FeatureRead)
def area_terrain(area_id: uuid.UUID, db: Session = Depends(get_db)) -> FeatureRead:
    return _group(db, area_id, "terrain")


@router.get("/areas/{area_id}/soil", response_model=FeatureRead)
def area_soil(area_id: uuid.UUID, db: Session = Depends(get_db)) -> FeatureRead:
    return _group(db, area_id, "soil")


@router.get("/areas/{area_id}/land-cover", response_model=FeatureRead)
def area_land_cover(area_id: uuid.UUID, db: Session = Depends(get_db)) -> FeatureRead:
    return _group(db, area_id, "land_cover")


@router.get("/areas/{area_id}/rainfall", response_model=RainfallRead)
def area_rainfall(area_id: uuid.UUID, db: Session = Depends(get_db)) -> RainfallRead:
    _area(db, area_id)
    return queries.rainfall_read(db, area_id)


def _events(db: Session, area: MonitoredArea, group: str, limit: int, offset: int) -> EventsRead:
    _, rows = queries.latest_features(db, area.id)
    summary = (rows[group].values if group in rows else {}) or {}
    if group == "historical_landslides":
        model, limits = LandslideEvent, HIST_LIMITS
        catalog_total = db.scalar(select(func.count()).select_from(LandslideEvent)) or 0
    else:
        model, limits = EarthquakeEvent, SEISMIC_LIMITS
        catalog_total = db.scalar(select(func.count()).select_from(EarthquakeEvent)) or 0
    empty = {"type": "FeatureCollection", "features": []}
    if catalog_total == 0:
        note = "catalog not imported" if group == "historical_landslides" else "no earthquake records fetched yet"
        return EventsRead(area_id=area.id, status="NOT_AVAILABLE", total=0, geojson=empty, summary={"reason": note}, limitations=limits)
    cond = func.ST_Intersects(model.geometry, area.geometry)
    total = db.scalar(select(func.count()).select_from(model).where(cond)) or 0
    feats = []
    if group == "historical_landslides":
        q = select(LandslideEvent).where(cond).order_by(LandslideEvent.event_date.desc().nulls_last()).offset(offset).limit(limit)
        for r in db.scalars(q):
            feats.append({"type": "Feature", "geometry": mapping(to_shape(r.geometry)),
                          "properties": {"id": r.external_event_id, "date": r.event_date.isoformat() if r.event_date else None,
                                         "location": r.location_name, "country": r.country, "trigger": r.trigger,
                                         "type": r.landslide_type, "source": r.source, "dataset_version": r.dataset_version}})
    else:
        q = select(EarthquakeEvent).where(cond).order_by(EarthquakeEvent.event_time.desc()).offset(offset).limit(limit)
        for r in db.scalars(q):
            feats.append({"type": "Feature", "geometry": mapping(to_shape(r.geometry)),
                          "properties": {"id": r.external_id, "time": r.event_time.isoformat(), "magnitude": r.magnitude,
                                         "depth_km": r.depth_km, "place": r.place, "url": r.url, "status": r.status}})
    return EventsRead(area_id=area.id, status="PROCESSED", total=total, geojson={"type": "FeatureCollection", "features": feats},
                      summary=json_safe(summary) or {"count": total}, limitations=limits)


@router.get("/areas/{area_id}/historical-landslides", response_model=EventsRead)
def area_historical(area_id: uuid.UUID, limit: int = Query(500, ge=1, le=2000), offset: int = Query(0, ge=0),
                    db: Session = Depends(get_db)) -> EventsRead:
    return _events(db, _area(db, area_id), "historical_landslides", limit, offset)


@router.get("/areas/{area_id}/seismic", response_model=EventsRead)
def area_seismic(area_id: uuid.UUID, limit: int = Query(500, ge=1, le=2000), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db)) -> EventsRead:
    return _events(db, _area(db, area_id), "seismic", limit, offset)


@router.post("/areas/{area_id}/seismic/refresh", response_model=SeismicRefreshResponse,
             summary="Explicit user action: fetch USGS earthquakes for the area's bounding box and store new ones")
def seismic_refresh(area_id: uuid.UUID, body: SeismicRefreshRequest, db: Session = Depends(get_db),
                    usgs: USGSEarthquakeProvider = Depends(get_usgs)) -> SeismicRefreshResponse:
    area = _area(db, area_id)
    w, s, e, n = to_shape(area.geometry).bounds
    start = datetime.combine(body.start_date, time.min, UTC)
    end = datetime.combine(body.end_date, time.max, UTC)
    try:
        res = usgs.fetch((w, s, e, n), start, end, body.min_magnitude)
    except (EnvError, NotAvailable) as exc:
        raise UpstreamError(f"USGS request failed: {exc}") from None
    except Exception as exc:  # network failure etc.: report, never fabricate
        raise UpstreamError(f"USGS request failed ({type(exc).__name__})") from None
    ids = [ev["id"] for ev in res.events]
    existing = set(db.scalars(select(EarthquakeEvent.external_id).where(EarthquakeEvent.source == "USGS",
                                                                          EarthquakeEvent.external_id.in_(ids)))) if ids else set()
    inserted = 0
    for ev in res.events:
        if ev["id"] in existing:
            continue
        db.add(EarthquakeEvent(source="USGS", external_id=ev["id"], event_time=ev["time"], magnitude=ev["magnitude"],
                               magnitude_type=ev.get("mag_type"), depth_km=ev.get("depth_km"), place=ev.get("place"), url=ev.get("url"),
                               status=ev.get("status"), geometry=from_shape(Point(ev["lon"], ev["lat"]), srid=4326),
                               original_attributes=json_safe(ev.get("properties") or {})))
        inserted += 1
    db.commit()
    warns = list(res.warnings) + (["result truncated at the provider's record cap"] if res.truncated else [])
    return SeismicRefreshResponse(area_id=area_id, fetched=len(res.events), inserted=inserted,
                                  duplicates=len(res.events) - inserted, warnings=warns)


@router.get("/areas/{area_id}/manifest", response_model=ManifestRead,
            summary="Stack manifest: every dataset with kind, static|dynamic, grid, provenance and coverage")
def area_manifest(area_id: uuid.UUID, db: Session = Depends(get_db)) -> ManifestRead:
    _area(db, area_id)
    return ManifestRead.model_validate(manifest_mod.build_manifest(db, area_id))


@router.get("/areas/{area_id}/quality-report", response_model=QualityReportRead)
def area_quality(area_id: uuid.UUID, db: Session = Depends(get_db)) -> QualityReportRead:
    _area(db, area_id)
    run = db.scalars(select(EnvironmentalProcessingRun).where(
        EnvironmentalProcessingRun.area_id == area_id, EnvironmentalProcessingRun.completed_at.is_not(None))
        .order_by(EnvironmentalProcessingRun.completed_at.desc())).first()
    if run is None or not run.quality_report:
        return QualityReportRead(area_id=area_id, run_id=None, report={
            "status": "NOT_RUN", "validation_status": "NOT_VALIDATED", "real_data_validation": "NOT_PERFORMED",
            "passed_checks": [], "failed_checks": [], "warnings": ["no processing run has completed for this area"],
            "missing_datasets": [], "layers": []})
    return QualityReportRead(area_id=area_id, run_id=run.id, report=run.quality_report)
