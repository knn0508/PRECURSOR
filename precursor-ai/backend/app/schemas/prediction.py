"""Phase 7 ML-slot schemas (ADR-0008). Contracts only: no model exists, nothing here produces a value.

The INPUT contract is the Phase 5 `ModelInputSpec`; `RiskModelInput` wraps it and does not define a second schema.
"""
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.features_cv.schema import ModelInputSpec
from app.services.features_cv.types import FeatureError

Head = Literal["susceptibility", "trigger"]
PredictionState = Literal["MODEL_NOT_TRAINED", "OK"]


class RiskModelInput(BaseModel):
    """What a predictor is asked to score: an area, a head, and the feature spec it must be fed (a `ModelInputSpec` dict)."""

    head: Head
    area_id: uuid.UUID
    input_spec: dict[str, Any]  # ModelInputSpec.to_dict(); validated by reconstructing the dataclass
    reference_time: datetime | None = None  # trigger head: the "now" of the forecast
    horizon_days: int | None = Field(default=None, gt=0)  # trigger head: stated lead time / horizon

    @field_validator("input_spec")
    @classmethod
    def _spec_is_model_input_spec(cls, v: dict[str, Any]) -> dict[str, Any]:
        try:
            ModelInputSpec(**v)
        except (FeatureError, TypeError) as exc:
            raise ValueError(f"input_spec is not a valid ModelInputSpec: {exc}") from exc
        return v

    @property
    def spec(self) -> ModelInputSpec:
        return ModelInputSpec(**self.input_spec)


class CalibrationInfo(BaseModel):
    calibrated: bool
    method: str | None = None  # e.g. isotonic, platt; None when not calibrated
    reference: str | None = None  # path/id of the calibration report


class ValidTime(BaseModel):
    start: datetime
    end: datetime | None = None


class RiskModelOutput(BaseModel):
    """What a registered model returns. Only a real, validated model may fill this; `risk_class` follows calibrated probabilities."""

    model_config = ConfigDict(protected_namespaces=())
    model_id: str
    model_version: str
    head: Head
    area_id: uuid.UUID
    probability: float = Field(ge=0.0, le=1.0)
    risk_class: str | None = None
    calibration: CalibrationInfo
    uncertainty: dict[str, Any] | None = None
    training_data_provenance: dict[str, Any]
    valid_region: dict[str, Any]  # GeoJSON geometry or bbox
    valid_time: ValidTime
    reference_time: datetime | None = None
    horizon_days: int | None = None


class ModelRegistryEntry(BaseModel):
    """A model that passed registry checks (model card, provenance, valid region/time, input spec)."""

    model_config = ConfigDict(protected_namespaces=())
    model_id: str
    version: str
    heads: list[Head]
    model_card: str
    training_data_provenance: dict[str, Any]
    valid_region: dict[str, Any]
    valid_time: ValidTime
    input_spec: dict[str, Any]
    metadata_schema_version: str


class RefusedModel(BaseModel):
    path: str
    reason: str


class PredictionResponse(BaseModel):
    status: PredictionState
    backend: str
    head: Head
    message: str
    output: RiskModelOutput | None = None  # always None under MODEL_NOT_TRAINED


class PredictionRequest(BaseModel):
    """Body of POST /prediction/{head}. The input spec comes from the registered model, never from the client."""

    area_id: uuid.UUID
    reference_time: datetime | None = None
    horizon_days: int | None = Field(default=None, gt=0)


class PredictionStatus(BaseModel):
    backend: str
    status: PredictionState
    registered_models: int
    refused_models: int
    message: str
