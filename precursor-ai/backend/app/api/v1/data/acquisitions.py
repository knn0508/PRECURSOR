import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.data.deps import acquisition_read
from app.core.exceptions import NotFoundError
from app.database.session import get_db
from app.models import DataAcquisition
from app.schemas.data_acquisition import AcquisitionList, AcquisitionRead, AcquisitionStatus, Maturity
from app.services.data_acquisition.metadata_service import MetadataRegistrationService

router = APIRouter()


@router.get("/acquisitions", response_model=AcquisitionList, summary="Registered granules (metadata and downloaded)")
def list_acquisitions(
    monitored_area_id: uuid.UUID | None = None,
    product_type: str | None = None,
    status: AcquisitionStatus | None = None,
    maturity: Maturity | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> AcquisitionList:
    rows, total = MetadataRegistrationService(db).list_acquisitions(
        product_type=product_type, status=status, maturity=maturity, area=monitored_area_id,
        start=start_date, end=end_date, offset=offset, limit=limit)
    return AcquisitionList(items=[acquisition_read(a) for a in rows], total=total)


@router.get("/acquisitions/{acquisition_id}", response_model=AcquisitionRead)
def get_acquisition(acquisition_id: uuid.UUID, db: Session = Depends(get_db)) -> AcquisitionRead:
    acq = db.get(DataAcquisition, acquisition_id)
    if acq is None:
        raise NotFoundError(f"Acquisition {acquisition_id} not found")
    return acquisition_read(acq)
