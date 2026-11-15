from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.data.deps import invalid_as_422
from app.core.config import Settings, get_settings
from app.core.exceptions import UpstreamError, ValidationFailed
from app.database.session import get_db
from app.schemas.data_acquisition import LandslideEventList, LandslideImportRequest, LandslideImportResponse
from app.services.data_acquisition.providers import landslide_catalog as lc

router = APIRouter()


def _bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if raw is None:
        return None
    try:
        w, s, e, n = (float(p) for p in raw.split(","))
    except ValueError:
        raise ValidationFailed("bbox must be min_lon,min_lat,max_lon,max_lat (four numbers)") from None
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValidationFailed("bbox is out of range or min is not below max")
    return w, s, e, n


@router.get("/landslide-events", response_model=LandslideEventList,
            summary="NASA Global Landslide Catalog events (historical reference only)")
def list_events(
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    date_from: datetime | None = None, date_to: datetime | None = None, country: str | None = None,
    offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db),
) -> LandslideEventList:
    rows, total = lc.list_events(
        db, bbox=_bbox(bbox), date_from=date_from, date_to=date_to, country=country, limit=limit, offset=offset)
    return LandslideEventList(items=[lc.to_read_schema(r) for r in rows], total=total, limitations=lc.LIMITATIONS)


@router.post("/landslide-events/import", response_model=LandslideImportResponse,
             summary="Import the catalog (downloads ~MB from the official NASA URL unless file_path is given)")
def import_events(
    body: LandslideImportRequest, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> LandslideImportResponse:
    try:
        with invalid_as_422():
            return lc.LandslideCatalogProvider(settings, db).run_import(
                force_download=body.force, file_path=body.file_path, allowed_root=settings.data_root)
    except OSError as exc:  # unreadable local file_path
        raise ValidationFailed(f"cannot read file: {exc}") from None
    except RuntimeError as exc:  # fetch() raises this after exhausting retries
        raise UpstreamError(str(exc)) from None
