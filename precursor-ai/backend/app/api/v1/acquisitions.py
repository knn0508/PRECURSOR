from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database.session import get_db
from app.models import SatelliteAcquisition
from app.repositories.satellite_repository import SatelliteAcquisitionRepository
from app.schemas.acquisition import AcquisitionList, AcquisitionRead

router = APIRouter(prefix="/acquisitions", tags=["acquisitions"])


@router.get("", response_model=AcquisitionList, summary="Latest satellite acquisition records (metadata only)")
def list_acquisitions(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)) -> AcquisitionList:
    stmt = (
        select(SatelliteAcquisition)
        .options(joinedload(SatelliteAcquisition.source))
        .order_by(SatelliteAcquisition.acquisition_date.desc())
        .limit(limit)
    )
    rows = db.scalars(stmt).all()
    items = [
        AcquisitionRead(
            id=a.id,
            satellite_source=a.source.name,
            area_id=a.area_id,
            acquisition_date=a.acquisition_date,
            orbit_direction=a.orbit_direction,
            polarization=a.polarization,
            product_type=a.product_type,
            processing_status=a.processing_status,
        )
        for a in rows
    ]
    return AcquisitionList(items=items, total=SatelliteAcquisitionRepository(db).count())
