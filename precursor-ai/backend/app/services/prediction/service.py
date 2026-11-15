"""PredictionService: the only place that decides between MODEL_NOT_TRAINED and a real answer."""
import uuid
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.schemas.uncertainty import ExplainRequest, ExplainResponse
from app.schemas.prediction import Head, PredictionRequest, PredictionResponse, PredictionStatus, RiskModelInput
from app.services.features_cv.pipeline import read_features_manifest
from app.services.features_cv.types import FeatureError, NotAvailable
from app.services.prediction.predictor import ModelNotTrained, NullPredictor
from app.services.prediction.registry import ModelRegistry

NOT_TRAINED = "No model is trained or registered. This is not a prediction and not a risk assessment."


class PredictionService:
    def __init__(self, backend: str, registry: ModelRegistry, data_root: Path):
        self.backend, self.registry, self.data_root = backend, registry, data_root

    def status(self) -> PredictionStatus:
        usable = self.backend == "registered_model" and any(self.registry.find_predictor(h) for h in ("susceptibility", "trigger"))
        return PredictionStatus(backend=self.backend, status="OK" if usable else "MODEL_NOT_TRAINED", registered_models=len(self.registry.entries),
                                refused_models=len(self.registry.refused), message="a registered model is active" if usable else NOT_TRAINED)

    def predict(self, head: Head, req: PredictionRequest) -> PredictionResponse:
        found = self.registry.find_predictor(head) if self.backend == "registered_model" else None
        entry, predictor = found if found else (None, NullPredictor())
        if entry is None:  # NullPredictor path: nothing to validate, nothing to score
            try:
                predictor.predict(None, {})  # type: ignore[arg-type]
            except ModelNotTrained:
                return PredictionResponse(status="MODEL_NOT_TRAINED", backend=self.backend, head=head, message=NOT_TRAINED)
        model_input = RiskModelInput(head=head, area_id=req.area_id, input_spec=entry.input_spec,
                                     reference_time=req.reference_time, horizon_days=req.horizon_days)
        manifest = self._manifest(req.area_id)
        model_input.spec.validate_against(manifest)  # raises FeatureError: no silent resampling / missing features
        try:
            out = predictor.predict(model_input, manifest)
        except ModelNotTrained:
            return PredictionResponse(status="MODEL_NOT_TRAINED", backend=self.backend, head=head, message=NOT_TRAINED)
        return PredictionResponse(status="OK", backend=self.backend, head=head, message="model output", output=out)

    def explain(self, req: ExplainRequest) -> ExplainResponse:
        found = self.registry.find_explainer(req.head) if self.backend == "registered_model" else None
        if found is None:
            return ExplainResponse(status="MODEL_NOT_AVAILABLE", message="No model with an explainer is available. No explanation exists.")
        entry, spec, explainer = found
        if req.scope not in spec["scopes"]:
            raise FeatureError(f"explainer does not support scope {req.scope!r}")
        model_input = RiskModelInput(head=req.head, area_id=req.area_id, input_spec=entry.input_spec, reference_time=req.reference_time)
        manifest = self._manifest(req.area_id)
        model_input.spec.validate_against(manifest)
        return ExplainResponse(status="OK", message="explanation of model behaviour (not causal)",
                               explanation=explainer.explain(model_input, manifest, req.scope, req.cell))

    def _manifest(self, area_id: uuid.UUID) -> dict[str, Any]:
        try:
            return read_features_manifest(self.data_root, area_id)
        except NotAvailable as exc:
            raise FeatureError(f"features manifest not available for this area: {exc}") from exc


def build_service(settings: Settings) -> PredictionService:
    return PredictionService(settings.prediction_backend, ModelRegistry(settings.models_dir), settings.data_root)
