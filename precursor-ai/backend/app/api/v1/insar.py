"""/api/v1/insar: inspect and process ALREADY-DOWNLOADED products. Never downloads, never touches credentials,
never accepts a filesystem path."""
from __future__ import annotations

import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import FileResponse
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError, ValidationFailed
from app.database.session import SessionLocal, get_db
from app.models import DeformationProduct, InSARProcessingRun
from app.schemas.insar import (
    DeformationList, DeformationRead, InputRef, ProcessableProduct, ProcessingConfigIn, ProductList, RunCreate,
    RunCreateResponse, RunList, RunRead, RunStatusRead, RunSummary,
)
from app.services.insar import storage
from app.services.insar.outputs import preview_png
from app.services.insar.runs import InSARRunService
from app.services.insar.types import TERMINAL, ProcessingConfig, ProcessingError, RunStatus

router = APIRouter(prefix="/insar", tags=["insar"])

_LABELS = {
    "SYNTHETIC_FIXTURE": "SYNTHETIC TEST DATA: not a satellite observation",
    "REAL_SATELLITE": "Derived from registered satellite data; NOT scientifically validated",
    "LOCAL_UNVERIFIED": "Local file of unverified provenance; NOT scientifically validated",
}


@lru_cache
def get_insar_service() -> InSARRunService:
    return InSARRunService(SessionLocal, get_settings())


def _run(db: Session, run_id: uuid.UUID) -> InSARProcessingRun:
    run = db.get(InSARProcessingRun, run_id, populate_existing=True)
    if run is None:
        raise NotFoundError(f"Processing run {run_id} not found")
    return run


def _prod_read(p: DeformationProduct) -> DeformationRead:
    fp = mapping(to_shape(p.footprint)) if p.footprint is not None else None
    return DeformationRead.model_validate(p).model_copy(update={"footprint": fp, "label": _LABELS.get(p.data_origin, "")})


def _cfg(c: ProcessingConfigIn) -> ProcessingConfig:
    return ProcessingConfig(**c.model_dump())


def _ref(product_id: str) -> InputRef:
    try:
        if product_id.startswith("sample:"):
            return InputRef(sample_file=product_id.removeprefix("sample:"))
        return InputRef(acquisition_id=uuid.UUID(product_id))
    except ValueError:
        raise ValidationFailed("invalid product id") from None


@router.get("/products", response_model=ProductList, summary="Local SAR products that can be inspected/processed")
def list_products(db: Session = Depends(get_db), svc: InSARRunService = Depends(get_insar_service)) -> ProductList:
    items = [
        ProcessableProduct(
            id=str(a.id), source="ACQUISITION", name=a.local_file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
            product_type=a.product_type, data_origin_hint="Phase 2 acquisition (downloaded file)",
            size_bytes=a.file_size_bytes, acquisition_start=a.acquisition_start, maturity=a.maturity)
        for a in svc.eligible_acquisitions(db)
    ]
    items += [
        ProcessableProduct(
            id=f"sample:{s['name']}", source="SAMPLE", name=s["name"], product_type=s["product_kind"],
            data_origin_hint="local file in data/samples/insar; origin is determined when inspected",
            size_bytes=s["size_bytes"])
        for s in svc.list_samples()
    ]
    return ProductList(items=items, note=(
        "Only files already on disk are listed. Metadata-only catalog hits are not processable; "
        "nothing is downloaded automatically."))


@router.get("/products/{product_id}", summary="Inspect one local product (reads metadata only)")
def inspect_one(product_id: str, db: Session = Depends(get_db), svc: InSARRunService = Depends(get_insar_service)) -> dict:
    return _inspect(_ref(product_id), db, svc)


@router.post("/inspect", summary="Inspect a selected local input")
def inspect_post(body: InputRef, db: Session = Depends(get_db), svc: InSARRunService = Depends(get_insar_service)) -> dict:
    return _inspect(body, db, svc)


def _inspect(ref: InputRef, db: Session, svc: InSARRunService) -> dict:
    try:
        return svc.inspect(db, ref.acquisition_id, ref.sample_file).to_dict()
    except (ProcessingError, FileNotFoundError):
        raise NotFoundError("input file not found") from None


@router.post("/processing-runs", response_model=RunCreateResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="Create a processing run on an existing local input")
def create_run(body: RunCreate, response: Response, db: Session = Depends(get_db),
               svc: InSARRunService = Depends(get_insar_service)) -> RunCreateResponse:
    run, created = svc.create_run(db, body.acquisition_id, body.sample_file, _cfg(body.config), force=body.force)
    if created:
        svc.submit(run.id)
        db.refresh(run)
    else:
        response.status_code = status.HTTP_200_OK
    return RunCreateResponse(run=RunSummary.model_validate(run), created=created)


@router.get("/processing-runs", response_model=RunList)
def list_runs(status_: RunStatus | None = Query(None, alias="status"), offset: int = Query(0, ge=0),
              limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)) -> RunList:
    q = select(InSARProcessingRun)
    cq = select(func.count()).select_from(InSARProcessingRun)
    if status_:
        q, cq = q.where(InSARProcessingRun.status == status_.value), cq.where(InSARProcessingRun.status == status_.value)
    rows = db.scalars(q.order_by(InSARProcessingRun.created_at.desc()).offset(offset).limit(limit)).all()
    return RunList(items=[RunSummary.model_validate(r) for r in rows], total=db.scalar(cq) or 0)


@router.get("/processing-runs/{run_id}", response_model=RunRead)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db)) -> RunRead:
    run = _run(db, run_id)
    return RunRead(**RunSummary.model_validate(run).model_dump(), stages=run.stages, config=run.config,
                   warnings=run.warnings, products=[_prod_read(p) for p in run.products])


@router.get("/processing-runs/{run_id}/status", response_model=RunStatusRead)
def run_status(run_id: uuid.UUID, db: Session = Depends(get_db)) -> RunStatusRead:
    r = _run(db, run_id)
    return RunStatusRead(id=r.id, status=r.status, current_stage=r.current_stage, progress=r.progress,
                         error_message=r.error_message, terminal=RunStatus(r.status) in TERMINAL, stages=r.stages)


@router.get("/processing-runs/{run_id}/quality", summary="Quality report (also written for failed/blocked runs)")
def run_quality(run_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    r = _run(db, run_id)
    if not r.quality_report:
        raise NotFoundError("no quality report yet: the run has not finished")
    return r.quality_report


@router.post("/processing-runs/{run_id}/cancel", response_model=RunSummary)
def cancel_run(run_id: uuid.UUID, db: Session = Depends(get_db), svc: InSARRunService = Depends(get_insar_service)):
    return RunSummary.model_validate(svc.cancel(db, run_id))


@router.get("/deformation-products", response_model=DeformationList)
def list_products_out(product_type: str | None = None, run_id: uuid.UUID | None = None,
                      offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
                      db: Session = Depends(get_db)) -> DeformationList:
    q, cq = select(DeformationProduct), select(func.count()).select_from(DeformationProduct)
    for cond in ([DeformationProduct.product_type == product_type] if product_type else []) + (
            [DeformationProduct.run_id == run_id] if run_id else []):
        q, cq = q.where(cond), cq.where(cond)
    rows = db.scalars(q.order_by(DeformationProduct.created_at.desc()).offset(offset).limit(limit)).all()
    return DeformationList(items=[_prod_read(p) for p in rows], total=db.scalar(cq) or 0)


def _product(db: Session, product_id: uuid.UUID) -> DeformationProduct:
    p = db.get(DeformationProduct, product_id)
    if p is None:
        raise NotFoundError(f"Deformation product {product_id} not found")
    return p


@router.get("/deformation-products/{product_id}", response_model=DeformationRead)
def get_product(product_id: uuid.UUID, db: Session = Depends(get_db)) -> DeformationRead:
    return _prod_read(_product(db, product_id))


def _file(p: DeformationProduct, settings: Settings):
    try:
        f = storage.resolve_output(settings.data_root, p.file_path)
    except ProcessingError:
        raise NotFoundError("raster not available") from None
    if not f.is_file():
        raise NotFoundError("raster file is missing on disk")
    return f


@router.get("/deformation-products/{product_id}/raster", summary="The registered GeoTIFF/COG (by id only)")
def get_raster(product_id: uuid.UUID, db: Session = Depends(get_db),
               settings: Settings = Depends(get_settings)) -> FileResponse:
    p = _product(db, product_id)
    return FileResponse(_file(p, settings), media_type="image/tiff", filename=f"{p.product_type.lower()}_{p.id}.tif",
                        headers={"X-Data-Origin": p.data_origin, "X-Units": p.units})


@router.get("/deformation-products/{product_id}/preview", summary="Quick-look PNG (diverging scale, nodata transparent)")
def get_preview(product_id: uuid.UUID, vmax: float | None = Query(None, gt=0), db: Session = Depends(get_db),
                settings: Settings = Depends(get_settings)) -> Response:
    p = _product(db, product_id)
    png = preview_png(_file(p, settings), vmax=vmax, diverging=p.product_type != "COHERENCE")
    return Response(png, media_type="image/png", headers={
        "X-Data-Origin": p.data_origin, "X-Units": p.units, "X-Scale": f"vmax={'auto(p98)' if vmax is None else vmax}"})
