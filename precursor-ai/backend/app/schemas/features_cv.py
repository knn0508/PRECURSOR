"""Read-only response schemas for Phase 5 (feature manifest, dataset summary, schema catalogue)."""
from typing import Any

from pydantic import BaseModel, ConfigDict


class FeatureSchemaRead(BaseModel):
    feature_schema_version: str
    dataset_schema_version: str
    code_version: str
    extractors: list[str]
    features: list[dict[str, Any]]
    notes: list[str]


class FeaturesManifestRead(BaseModel):
    model_config = ConfigDict(extra="allow")  # the manifest is a documented JSON file; keys are passed through unchanged

    feature_schema_version: str
    code_version: str
    generated_at: str
    area_id: str
    grid: dict[str, Any]
    features: list[dict[str, Any]]
    counts: dict[str, int]
    contains_synthetic_data: bool
    validation_status: str
    real_data_validation: str
    notes: list[str]


class DatasetSummaryRead(BaseModel):
    model_config = ConfigDict(extra="allow")

    dataset_schema_version: str
    feature_schema_version: str
    code_version: str
    generated_at: str
    area_id: str
    seed: int | None = None
    contains_synthetic_data: bool
    counts: dict[str, Any]
    class_balance: dict[str, Any]
    split: dict[str, Any]
    leakage: dict[str, Any]
    lead_time_anchors_days: list[int]
    dynamic_columns: list[dict[str, Any]]
    caveats: list[str]
    warnings: list[str]
    validation_status: str
    real_data_validation: str
