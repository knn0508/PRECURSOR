"""Read-only displacement-forecast endpoints (ADR-0011). Serves a precomputed research bundle; never runs a model."""
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse, PlainTextResponse

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.database.session import get_db
from app.services.area_service import AreaService
from app.services.displacement_forecast import store

router = APIRouter(prefix="/displacement-forecast", tags=["displacement-forecast"])


def _nf(exc: Exception) -> NotFoundError:
    return NotFoundError(str(exc.args[0]) if exc.args else "not found")


@router.get("/status")
def status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return store.status(settings.data_root)


@router.get("/metrics")
def metrics(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        return store.metrics(settings.data_root)
    except FileNotFoundError as exc:
        raise _nf(exc) from exc


@router.get("/forecast")
def forecast(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        return store.forecast_grid(settings.data_root)
    except FileNotFoundError as exc:
        raise _nf(exc) from exc


@router.get("/images/{name}")
def image(name: str, settings: Settings = Depends(get_settings)) -> FileResponse:
    try:
        return FileResponse(store.image_path(settings.data_root, name), media_type="image/png")
    except (KeyError, FileNotFoundError) as exc:
        raise _nf(exc) from exc


@router.get("/docs/{name}", response_class=PlainTextResponse)
def doc(name: str, settings: Settings = Depends(get_settings)) -> str:
    try:
        return store.doc_text(settings.data_root, name)
    except (KeyError, FileNotFoundError) as exc:
        raise _nf(exc) from exc


@router.get("/backtest")
def backtest(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        return store.backtest_meta(settings.data_root)
    except FileNotFoundError as exc:
        raise _nf(exc) from exc


@router.get("/backtest/{issue}")
def backtest_issue(issue: str, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        return store.backtest_grids(settings.data_root, issue)
    except (KeyError, FileNotFoundError) as exc:
        raise _nf(exc) from exc


@router.get("/areas/{area_id}/backtest")
def area_backtest(area_id: uuid.UUID, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Backtest result attached to a monitored area, ONLY if the data footprint covers it; otherwise covered=false and no result."""
    area = AreaService(db).get_area(area_id)
    try:
        cov = store.area_coverage(settings.data_root, area.geometry)
        if not cov["covered"]:
            return {"area_id": str(area_id), "area_name": area.name, "label": store.LABEL, **cov, "result": None,
                    "reason": "The OPERA frame F16940 footprint does not cover this area; no forecast or backtest exists for it."}
        return {"area_id": str(area_id), "area_name": area.name, **cov, "result": store.backtest_meta(settings.data_root)}
    except FileNotFoundError as exc:
        raise _nf(exc) from exc
