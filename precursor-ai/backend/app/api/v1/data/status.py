from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.data.deps import get_auth, get_providers
from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.schemas.data_acquisition import DataStatus
from app.services.data_acquisition.status_service import compute_status

router = APIRouter()


@router.get("/status", response_model=DataStatus, summary="Data acquisition status (no secrets)")
def data_status(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
    auth=Depends(get_auth), providers=Depends(get_providers),
) -> DataStatus:
    return compute_status(settings, auth, providers, db)
