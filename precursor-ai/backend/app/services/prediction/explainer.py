"""Explainer protocol (Phase 8). No explainer exists: nothing here runs SHAP/LIME or any attribution method."""
from typing import Any, Protocol, runtime_checkable

from app.schemas.prediction import RiskModelInput
from app.schemas.uncertainty import Explanation, Scope


@runtime_checkable
class Explainer(Protocol):
    model_id: str
    version: str

    def explain(self, model_input: RiskModelInput, features_manifest: dict[str, Any], scope: Scope, cell: dict[str, int] | None) -> Explanation: ...
