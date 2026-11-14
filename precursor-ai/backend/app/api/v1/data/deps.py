"""Process-wide singletons and shared helpers for /data routes. Every dependency is overridable in tests."""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import lru_cache

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationFailed
from app.database.session import SessionLocal
from app.models import DataAcquisition, DownloadJob, MonitoredArea
from app.schemas.data_acquisition import AcquisitionRead, AOIInput, DownloadJobRead
from app.services.data_acquisition.aoi import AOI
from app.services.data_acquisition.authentication import EarthdataAuthenticationService
from app.services.data_acquisition.download_manager import DownloadManager
from app.services.data_acquisition.orchestrator import AcquisitionOrchestrator
from app.services.data_acquisition.registry import build_providers
from app.services.data_acquisition.search_service import AcquisitionSearchService
from app.services.data_acquisition.validation_service import FileValidationService


@lru_cache
def get_auth() -> EarthdataAuthenticationService:
    return EarthdataAuthenticationService(get_settings())


@lru_cache
def get_download_manager() -> DownloadManager:
    return DownloadManager(get_settings())


@lru_cache
def get_validator() -> FileValidationService:
    return FileValidationService(get_settings())


@lru_cache
def get_providers() -> dict:
    return build_providers(get_settings(), get_auth(), get_download_manager())


@lru_cache
def get_orchestrator() -> AcquisitionOrchestrator:
    s = get_settings()
    return AcquisitionOrchestrator(
        SessionLocal, get_providers(), get_validator(), s,
        executor=ThreadPoolExecutor(s.max_concurrent_downloads, thread_name_prefix="dl"))


@lru_cache
def get_search_service() -> AcquisitionSearchService:
    return AcquisitionSearchService(get_providers(), SessionLocal, get_settings())


@contextmanager
def invalid_as_422():
    """AOIError is a ValueError, so this covers bad geometry, oversize AOIs, bad dates and maturities."""
    try:
        yield
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from None


def resolve_aoi(aoi_input: AOIInput, db: Session) -> tuple[AOI, uuid.UUID | None]:
    with invalid_as_422():
        if aoi_input.monitored_area_id:
            area = db.get(MonitoredArea, aoi_input.monitored_area_id)
            if area is None:
                raise NotFoundError(f"Monitored area {aoi_input.monitored_area_id} not found")
            return AOI.from_geometry(aoi_input.name or area.name, to_shape(area.geometry)), area.id
        return AOI.from_geojson(aoi_input.name or "aoi", aoi_input.geometry), None


def acquisition_read(a: DataAcquisition) -> AcquisitionRead:
    fp = mapping(to_shape(a.spatial_footprint)) if a.spatial_footprint is not None else None
    return AcquisitionRead.model_validate(a).model_copy(update={"footprint": fp})


def job_read(j: DownloadJob) -> DownloadJobRead:
    return DownloadJobRead.model_validate(j).model_copy(
        update={"granule_id": j.acquisition.granule_id, "product_type": j.acquisition.product_type})


def load_job(db: Session, job_id: uuid.UUID) -> DownloadJob | None:
    return db.get(DownloadJob, job_id, populate_existing=True)  # workers update rows from other sessions
