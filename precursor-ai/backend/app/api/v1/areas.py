import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.area import AreaCreate, AreaList, AreaRead
from app.services.area_service import AreaService

router = APIRouter(prefix="/areas", tags=["areas"])


@router.get("", response_model=AreaList)
def list_areas(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> AreaList:
    return AreaService(db).list_areas(offset, limit)


@router.get("/{area_id}", response_model=AreaRead)
def get_area(area_id: uuid.UUID, db: Session = Depends(get_db)) -> AreaRead:
    return AreaService(db).get_area(area_id)


@router.post("", response_model=AreaRead, status_code=status.HTTP_201_CREATED)
def create_area(payload: AreaCreate, db: Session = Depends(get_db)) -> AreaRead:
    return AreaService(db).create_area(payload)
