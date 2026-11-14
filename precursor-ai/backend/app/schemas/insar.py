"""Phase 3 API contracts. No endpoint takes a filesystem path: inputs are acquisition ids or bare sample names."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InputRef(BaseModel):
    acquisition_id: uuid.UUID | None = None
    sample_file: str | None = Field(default=None, max_length=200, description="bare file name in data/samples/insar")

    @model_validator(mode="after")
    def _one(self):
        if (self.acquisition_id is None) == (self.sample_file is None):
            raise ValueError("provide exactly one of acquisition_id or sample_file")
        return self


class ProcessingConfigIn(BaseModel):
    polarization: str | None = Field(default=None, pattern=r"^(HH|HV|VH|VV|RH|RV|LH|LV)$")
    coherence_threshold: float | None = Field(default=None, ge=0.0, le=1.0, description="None = no coherence masking")
    use_connected_components_mask: bool = False
    compute_velocity: bool = True
    block_rows: int = Field(default=256, ge=16, le=4096)
    keep_intermediates: bool = False


class RunCreate(InputRef):
    config: ProcessingConfigIn = Field(default_factory=ProcessingConfigIn)
    force: bool = Field(default=False, description="re-run even if an identical run exists")


class ProcessableProduct(BaseModel):
    id: str  # acquisition uuid, or "sample:<file name>"
    source: str  # ACQUISITION | SAMPLE
    name: str
    product_type: str
    data_origin_hint: str  # what is known WITHOUT opening the file
    size_bytes: int | None = None
    acquisition_start: datetime | None = None
    maturity: str | None = None


class ProductList(BaseModel):
    items: list[ProcessableProduct]
    note: str


class StageRead(BaseModel):
    name: str
    status: str
    message: str | None = None
    started_at: str | None = None
    ended_at: str | None = None


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    acquisition_id: uuid.UUID | None
    input_kind: str
    input_ref: str
    product_kind: str | None
    data_origin: str | None
    status: str
    current_stage: str | None
    progress: float
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class RunRead(RunSummary):
    stages: list[StageRead]
    config: dict[str, Any]
    warnings: list[str]
    products: list[DeformationRead] = []


class RunList(BaseModel):
    items: list[RunSummary]
    total: int


class RunCreateResponse(BaseModel):
    run: RunSummary
    created: bool = Field(description="False when an identical run already exists and was returned instead")


class RunStatusRead(BaseModel):
    id: uuid.UUID
    status: str
    current_stage: str | None
    progress: float
    error_message: str | None
    terminal: bool
    stages: list[StageRead]


class DeformationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    run_id: uuid.UUID
    acquisition_id: uuid.UUID | None
    product_type: str
    file_format: str
    file_size_bytes: int | None
    units: str
    crs: str | None
    width: int
    height: int
    reference_time: datetime | None
    secondary_time: datetime | None
    data_origin: str
    sign_convention: str | None
    scientifically_validated: bool
    statistics: dict[str, Any]
    footprint: Any = None  # GeoJSON dict (replaced from the PostGIS value in the route)
    label: str = ""
    created_at: datetime


class DeformationList(BaseModel):
    items: list[DeformationRead]
    total: int


RunRead.model_rebuild()
