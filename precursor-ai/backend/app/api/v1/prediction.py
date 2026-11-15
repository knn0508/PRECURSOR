"""Phase 7 ML-slot endpoints (ADR-0008). Under PREDICTION_BACKEND=none every one answers MODEL_NOT_TRAINED."""
from functools import lru_cache

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.exceptions import ValidationFailed
from app.schemas.uncertainty import ExplainRequest, ExplainResponse
from app.schemas.prediction import ModelRegistryEntry, PredictionRequest, PredictionResponse, PredictionStatus, RefusedModel
from app.services.features_cv.types import FeatureError
from app.services.prediction.service import PredictionService, build_service

router = APIRouter(prefix="/prediction", tags=["prediction"])


@lru_cache
def _service(backend: str, models_dir: str, data_root: str) -> PredictionService:
    return build_service(Settings(prediction_backend=backend, models_dir=models_dir, data_root=data_root))


def get_prediction_service(settings: Settings = Depends(get_settings)) -> PredictionService:
    svc = _service(settings.prediction_backend, str(settings.models_dir), str(settings.data_root))
    svc.registry.scan()  # pick up added/removed model folders without a restart; attached predictors are kept
    return svc


@router.get("/status", response_model=PredictionStatus)
def status(svc: PredictionService = Depends(get_prediction_service)) -> PredictionStatus:
    return svc.status()


@router.get("/models")
def models(svc: PredictionService = Depends(get_prediction_service)) -> dict[str, list[ModelRegistryEntry] | list[RefusedModel]]:
    return {"registered": svc.registry.entries, "refused": svc.registry.refused}


def _run(head: str, req: PredictionRequest, svc: PredictionService) -> PredictionResponse:
    try:
        return svc.predict(head, req)  # type: ignore[arg-type]
    except FeatureError as exc:
        raise ValidationFailed(str(exc)) from exc


@router.post("/susceptibility", response_model=PredictionResponse)
def susceptibility(req: PredictionRequest, svc: PredictionService = Depends(get_prediction_service)) -> PredictionResponse:
    return _run("susceptibility", req, svc)


@router.post("/trigger", response_model=PredictionResponse)
def trigger(req: PredictionRequest, svc: PredictionService = Depends(get_prediction_service)) -> PredictionResponse:
    return _run("trigger", req, svc)


@router.post("/explain", response_model=ExplainResponse)
def explain(req: ExplainRequest, svc: PredictionService = Depends(get_prediction_service)) -> ExplainResponse:
    try:
        return svc.explain(req)
    except FeatureError as exc:
        raise ValidationFailed(str(exc)) from exc
