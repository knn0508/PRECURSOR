"""Phase 8 read-only endpoint: data-quality uncertainty ledger for an area. No model, no predictive confidence."""
import uuid

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.schemas.uncertainty import UncertaintyReport
from app.services.features_cv.pipeline import read_features_manifest
from app.services.features_cv.types import NotAvailable
from app.services.uncertainty.ledger import build_report

router = APIRouter(prefix="/uncertainty", tags=["uncertainty"])


@router.get("/areas/{area_id}/report", response_model=UncertaintyReport)
def area_report(area_id: uuid.UUID, settings: Settings = Depends(get_settings)) -> UncertaintyReport:
    try:
        return build_report(area_id, read_features_manifest(settings.data_root, area_id))
    except NotAvailable as exc:
        raise NotFoundError(str(exc)) from exc
