"""Phase 8 schemas: uncertainty ledger and explainability interface. Metadata and contracts only; no model exists.

`UncertaintyReport` carries DATA-QUALITY facts propagated from Phases 2-6. It never contains a confidence number for a
prediction: predictive uncertainty is `NOT_ESTIMATED` until a real model and a real method exist.
"""
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["INFO", "WARNING", "LIMITATION"]
Scope = Literal["global", "local"]


class UncertaintyItem(BaseModel):
    code: str
    source_phase: int
    severity: Severity
    message: str
    value: float | None = None  # a measured quantity from the input metadata, never a made-up confidence


class SuppressionReason(BaseModel):
    code: str
    message: str


class UncertaintyReport(BaseModel):
    area_id: uuid.UUID
    items: list[UncertaintyItem]
    predictive_uncertainty: Literal["NOT_ESTIMATED"] = "NOT_ESTIMATED"
    suppressed: bool = False
    suppression_reasons: list[SuppressionReason] = []
    notes: list[str]


class FeatureContribution(BaseModel):
    feature: str
    contribution: float  # model-behaviour attribution in the model's output units; not causal
    units: str | None = None


class Explanation(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_id: str
    model_version: str
    head: Literal["susceptibility", "trigger"]
    scope: Scope
    method: str  # e.g. the explainer's declared method; recorded, never inferred
    background_dataset_ref: str
    contributions: list[FeatureContribution]
    cell: dict[str, int] | None = None  # local scope: {"row", "col"} on the reference grid
    caveats: list[str] = ["Describes model behaviour, not physical causation."]


class ExplainRequest(BaseModel):
    area_id: uuid.UUID
    head: Literal["susceptibility", "trigger"]
    scope: Scope = "global"
    cell: dict[str, int] | None = None
    reference_time: Any | None = Field(default=None, description="trigger head: forecast time")


class ExplainResponse(BaseModel):
    status: Literal["MODEL_NOT_AVAILABLE", "OK"]
    message: str
    explanation: Explanation | None = None  # always None under MODEL_NOT_AVAILABLE
