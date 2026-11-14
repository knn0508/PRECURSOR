import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.data.deps import get_orchestrator, job_read, load_job
from app.core.exceptions import ConflictError, NotFoundError
from app.database.session import get_db
from app.schemas.data_acquisition import (
    DownloadCreate, DownloadCreateResponse, DownloadJobList, DownloadJobRead, JobStatus)
from app.services.data_acquisition.metadata_service import MetadataRegistrationService
from app.services.data_acquisition.orchestrator import AcquisitionOrchestrator

router = APIRouter()


def _get(db: Session, job_id: uuid.UUID):
    job = load_job(db, job_id)
    if job is None:
        raise NotFoundError(f"Download job {job_id} not found")
    return job


@router.post("/downloads", response_model=DownloadCreateResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="Queue downloads for registered granules; returns immediately")
def create_downloads(
    body: DownloadCreate, db: Session = Depends(get_db), orch: AcquisitionOrchestrator = Depends(get_orchestrator),
) -> DownloadCreateResponse:
    plan = orch.plan_jobs(body.acquisition_ids)
    jobs = [job_read(_get(db, j.id)) for j in plan.jobs]
    return DownloadCreateResponse(jobs=jobs, skipped={str(k): v for k, v in plan.skipped.items()})


@router.get("/downloads", response_model=DownloadJobList)
def list_downloads(
    status: JobStatus | None = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> DownloadJobList:
    rows, total = MetadataRegistrationService(db).list_jobs(status=status, offset=offset, limit=limit)
    return DownloadJobList(items=[job_read(j) for j in rows], total=total)


@router.get("/downloads/{job_id}", response_model=DownloadJobRead)
def get_download(job_id: uuid.UUID, db: Session = Depends(get_db)) -> DownloadJobRead:
    return job_read(_get(db, job_id))


@router.post("/downloads/{job_id}/retry", response_model=DownloadJobRead, status_code=status.HTTP_202_ACCEPTED)
def retry_download(
    job_id: uuid.UUID, db: Session = Depends(get_db), orch: AcquisitionOrchestrator = Depends(get_orchestrator),
) -> DownloadJobRead:
    try:
        orch.retry_job(job_id)
    except LookupError:
        raise NotFoundError(f"Download job {job_id} not found") from None
    except ValueError as exc:
        raise ConflictError(str(exc)) from None
    return job_read(_get(db, job_id))
