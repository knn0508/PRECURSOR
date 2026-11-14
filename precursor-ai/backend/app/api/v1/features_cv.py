"""Phase 5 read-only endpoints: schema catalogue, feature manifest, dataset summary. Extraction/dataset runs are CLI/service only."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.database.session import get_db
from app.models import MonitoredArea
from app.schemas.features_cv import DatasetSummaryRead, FeatureSchemaRead, FeaturesManifestRead
from app.services.features_cv.dataset_run import read_dataset_summary
from app.services.features_cv.pipeline import read_features_manifest
from app.services.features_cv.registry import REGISTRY
from app.services.features_cv.types import DATASET_SCHEMA_VERSION, CODE_VERSION, FEATURE_SCHEMA_VERSION, NotAvailable

router = APIRouter(prefix="/features-cv", tags=["features-cv"])


def _area(db: Session, area_id: uuid.UUID) -> MonitoredArea:
    a = db.get(MonitoredArea, area_id)
    if a is None:
        raise NotFoundError("area not found")
    return a


@router.get("/schema", response_model=FeatureSchemaRead, summary="Versioned feature schema (static catalogue, no data needed)")
def feature_schema() -> FeatureSchemaRead:
    return FeatureSchemaRead(feature_schema_version=FEATURE_SCHEMA_VERSION, dataset_schema_version=DATASET_SCHEMA_VERSION, code_version=CODE_VERSION,
                             extractors=REGISTRY.names(), features=[s.to_dict() for s in REGISTRY.catalogue()],
                             notes=["Descriptive features only; nothing here is a risk score, probability or prediction."])


@router.get("/areas/{area_id}/features/manifest", response_model=FeaturesManifestRead)
def area_features_manifest(area_id: uuid.UUID, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> FeaturesManifestRead:
    _area(db, area_id)
    try:
        return FeaturesManifestRead.model_validate(read_features_manifest(settings.data_root, area_id))
    except NotAvailable as exc:
        raise NotFoundError(str(exc)) from exc


@router.get("/areas/{area_id}/datasets/summary", response_model=DatasetSummaryRead)
def area_dataset_summary(area_id: uuid.UUID, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> DatasetSummaryRead:
    _area(db, area_id)
    try:
        return DatasetSummaryRead.model_validate(read_dataset_summary(settings.data_root, area_id))
    except NotAvailable as exc:
        raise NotFoundError(str(exc)) from exc
