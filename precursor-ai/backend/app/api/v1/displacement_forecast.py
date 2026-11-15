"""Read-only displacement-forecast endpoints (ADR-0011). Serves a precomputed research bundle; never runs a model."""
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, PlainTextResponse

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
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
