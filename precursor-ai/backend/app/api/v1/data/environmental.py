from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.data.deps import get_orchestrator, get_search_service, invalid_as_422, job_read, load_job, resolve_aoi
from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.schemas.data_acquisition import EnvironmentalAcquireRequest, EnvironmentalAcquireResponse
from app.services.data_acquisition.environmental import acquire_environmental
from app.services.data_acquisition.orchestrator import AcquisitionOrchestrator
from app.services.data_acquisition.search_service import AcquisitionSearchService

router = APIRouter()


@router.post("/environmental/acquire", response_model=EnvironmentalAcquireResponse,
             summary="NASADEM + GPM (+ SMAP) for an AOI; dry run by default")
def acquire(
    req: EnvironmentalAcquireRequest, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
    search: AcquisitionSearchService = Depends(get_search_service),
    orch: AcquisitionOrchestrator = Depends(get_orchestrator),
) -> EnvironmentalAcquireResponse:
    aoi, area_id = resolve_aoi(req.aoi, db)
    with invalid_as_422():
        if req.start_date > req.end_date:
            raise ValueError("start_date must not be after end_date")
        out = acquire_environmental(
            search, orch, settings, aoi, req.start_date, req.end_date, include_smap=req.include_smap,
            dry_run=req.dry_run, max_granules=req.max_granules, monitored_area_id=area_id)
    return EnvironmentalAcquireResponse(
        dry_run=req.dry_run, results=out.results, jobs=[job_read(load_job(db, j.id)) for j in out.jobs],
        provider_errors=out.provider_errors, warnings=out.warnings)
