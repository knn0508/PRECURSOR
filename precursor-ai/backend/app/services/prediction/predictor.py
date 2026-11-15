"""Predictor protocol and the null implementation. The null predictor never returns a value."""
from typing import Any, Protocol, runtime_checkable

from app.schemas.prediction import Head, RiskModelInput, RiskModelOutput


class ModelNotTrained(Exception):
    """No model is available to answer. Mapped to the MODEL_NOT_TRAINED response, not to an error."""


@runtime_checkable
class Predictor(Protocol):
    model_id: str
    version: str
    heads: tuple[Head, ...]

    def predict(self, model_input: RiskModelInput, features_manifest: dict[str, Any]) -> RiskModelOutput: ...


class NullPredictor:
    model_id = "none"
    version = "0"
    heads: tuple[Head, ...] = ("susceptibility", "trigger")

    def predict(self, model_input: RiskModelInput, features_manifest: dict[str, Any]) -> RiskModelOutput:
        raise ModelNotTrained("no model is registered (PREDICTION_BACKEND=none or empty registry)")
