from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.session import check_database, get_db
from app.schemas.system import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> HealthResponse:
    db_ok = check_database(db)
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        app_name=settings.app_name,
        version=settings.app_version,
        database="connected" if db_ok else "unavailable",
    )
