"""Phase 4 API contracts (/api/v1/environmental). No schema exposes a filesystem path.

Every layer/feature carries `data_origin`, `measurement_kind` and `validation_status`. Nothing here is a risk score,
probability or prediction; environmental measurements are not landslide risk.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

ORIGINS = "REAL_SATELLITE | SYNTHETIC_FIXTURE | LOCAL_UNVERIFIED"


class LayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    area_id: uuid.UUID
    run_id: uuid.UUID | None
    layer_type: str  # ELEVATION SLOPE ASPECT RAINFALL SOIL LAND_COVER HISTORICAL_LANDSLIDES SEISMIC INSAR_*
    source_provider: str
    dataset_name: str
    dataset_version: str | None
    measurement_kind: str  # SOURCE_OBSERVATION | DERIVED_MEASUREMENT | STATISTICAL_SUMMARY
    data_origin: str = Field(description=ORIGINS)
    validation_status: str  # always NOT_VALIDATED in Phase 4
    status: str  # PROCESSED PARTIALLY_PROCESSED NOT_AVAILABLE FAILED ...
    units: str | None
    crs: str | None
    width: int | None
    height: int | None
    nodata: float | None
    native_resolution: dict[str, Any] | None
    processing_resolution: dict[str, Any] | None
    temporal_start: datetime | None
    temporal_end: datetime | None
    footprint: Any = None  # GeoJSON Polygon (EPSG:4326) or null
    provenance: dict[str, Any]
    quality: dict[str, Any]
    statistics: dict[str, Any]
    temporal_kind: str = "static"  # static | dynamic (stack metadata)
    aligned: bool = False  # a copy resampled to the reference grid exists
    has_raster: bool = False  # True when /layers/{id}/raster and /preview exist
    label: str = ""  # human label: synthetic / unverified / real-but-not-validated
    created_at: datetime


class LayerList(BaseModel):
    items: list[LayerRead]
    total: int


class LegendClass(BaseModel):
    id: int
    name: str
    color: str  # hex


class LegendRead(BaseModel):
    layer_id: uuid.UUID
    layer_type: str
    units: str | None
    kind: str  # continuous | circular | categorical
    vmin: float | None = None
    vmax: float | None = None
    colors: list[str] = Field(default_factory=list, description="hex colour stops, low to high, identical to the preview PNG ramp")
    classes: list[LegendClass] = []
    note: str = ""


class CoverageItem(BaseModel):
    layer_type: str
    available: bool
    status: str  # PROCESSED | PARTIALLY_PROCESSED | NOT_AVAILABLE | FAILED | NOT_RUN
    data_origin: str | None = None
    valid_percent: float | None = None
    missing_percent: float | None = None
    aoi_coverage_percent: float | None = None
    temporal_start: datetime | None = None
    temporal_end: datetime | None = None
    layer_id: uuid.UUID | None = None
    reason: str | None = None  # why a layer is NOT available (never filled with zeros)


class CoverageRead(BaseModel):
    area_id: uuid.UUID
    items: list[CoverageItem]
    missing_datasets: list[str]
    last_processed_at: datetime | None
    note: str = "Availability only. Nothing here is a risk assessment."


class ProcessConfig(BaseModel):
    stages: list[str] | None = Field(default=None, description="subset of stage names; null = all")
    force: bool = Field(default=False, description="redo stages even when identical inputs were already processed")
    start_date: date | None = Field(default=None, description="rainfall/seismic window start")
    end_date: date | None = None
    rolling_windows: list[int] = Field(default=[3, 7, 30], description="days; rolling sums need complete windows")
    include_insar: bool = True
    grid_crs: str | None = Field(default=None, pattern=r"^EPSG:\d{4,6}$",
                                 description="projected metre CRS for the reference grid; null = UTM zone chosen from the AOI")
    grid_resolution_m: float | None = Field(default=None, gt=0, le=10000, description="reference grid cell size in metres; null = 30 m (coarsened if the grid would be huge)")
    rainfall_resolution: str = Field(default="daily", pattern="^(daily|half_hourly)$", description="IMERG product used for rainfall; daily is the default")

    @model_validator(mode="after")
    def _dates(self):
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("give both start_date and end_date, or neither")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if self.start_date and self.end_date and (self.end_date - self.start_date).days > 3660:
            raise ValueError("date range longer than 10 years")
        if any(w < 1 or w > 366 for w in self.rolling_windows):
            raise ValueError("rolling window must be 1-366 days")
        return self


class StageRead(BaseModel):
    name: str
    status: str  # DONE PARTIAL NOT_AVAILABLE SKIPPED FAILED RUNNING
    message: str | None = None
    started_at: str | None = None
    ended_at: str | None = None


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    area_id: uuid.UUID
    status: str  # QUEUED RUNNING COMPLETED PARTIAL FAILED CANCELLED
    current_stage: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class RunRead(RunSummary):
    stages: list[StageRead]
    config: dict[str, Any]
    warnings: list[str]


class RunList(BaseModel):
    items: list[RunSummary]
    total: int


class RunCreateResponse(BaseModel):
    run: RunSummary


class FeatureRead(BaseModel):
    """Descriptive features of one group. `values` and `units` share keys. Never a score or prediction."""

    group: str  # terrain rainfall soil land_cover historical_landslides seismic insar
    status: str
    values: dict[str, Any]
    units: dict[str, str]
    lineage: list[dict[str, Any]]
    measurement_kind: str
    data_origin: str
    warnings: list[str]
    label: str = ""


class FeaturesRead(BaseModel):
    area_id: uuid.UUID
    run_id: uuid.UUID | None
    groups: list[FeatureRead]
    disclaimer: str = (
        "Descriptive measurements and summaries of source data. Not a landslide risk score, probability or prediction."
    )


class RainfallPoint(BaseModel):
    date: str  # YYYY-MM-DD (daily) or YYYY-MM (monthly)
    precipitation_mm: float | None  # null = NOT observed. Never zero-filled.
    observed: bool


class RainfallRead(BaseModel):
    area_id: uuid.UUID
    status: str
    data_origin: str | None
    source: str | None
    temporal_start: datetime | None
    temporal_end: datetime | None
    units: str = "mm"
    quantity: str = "accumulated precipitation (mm per day / per month), not a rate"
    daily: list[RainfallPoint]
    monthly: list[RainfallPoint]  # monthly total is null when any day of the month is missing
    rolling: dict[str, list[RainfallPoint]]  # "3d" "7d" "30d": null unless the whole window is observed
    observed_days: int
    missing_days: int
    notes: list[str] = []


class EventsRead(BaseModel):
    """Historical landslide catalog events or earthquakes inside the AOI (GeoJSON FeatureCollection)."""

    area_id: uuid.UUID
    status: str
    total: int
    geojson: dict[str, Any]
    summary: dict[str, Any]
    limitations: list[str]


class SeismicRefreshRequest(BaseModel):
    start_date: date
    end_date: date
    min_magnitude: float | None = Field(default=None, ge=0, le=10)

    @model_validator(mode="after")
    def _order(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if (self.end_date - self.start_date).days > 3660:
            raise ValueError("date range longer than 10 years")
        return self


class SeismicRefreshResponse(BaseModel):
    area_id: uuid.UUID
    fetched: int
    inserted: int
    duplicates: int
    warnings: list[str]


class QualityReportRead(BaseModel):
    area_id: uuid.UUID
    run_id: uuid.UUID | None
    report: dict[str, Any]


class DatasetInfo(BaseModel):
    layer_type: str
    provider: str
    dataset_name: str
    implementation_status: str  # IMPLEMENTED_AND_TESTED | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | PARTIALLY_IMPLEMENTED | PLACEHOLDER | BLOCKED
    description: str
    native_resolution: str | None = None
    temporal_resolution: str | None = None
    units: str | None = None
    access: str | None = None
    license: str | None = None
    limitations: list[str] = []


class DatasetList(BaseModel):
    items: list[DatasetInfo]


class ManifestEntry(BaseModel):
    """One dataset in the area's data stack. `kind` raster = a file on the reference grid; series/vector = non-raster."""

    layer_id: uuid.UUID | None
    layer_type: str
    kind: str  # raster | series | vector
    temporal_kind: str  # static | dynamic
    status: str
    units: str | None
    crs: str | None
    native_resolution: dict[str, Any] | None
    processing_resolution: dict[str, Any] | None
    on_reference_grid: bool  # raster only: an aligned copy exists
    source: dict[str, Any]  # provider, dataset_name, dataset_version
    temporal_start: datetime | None
    temporal_end: datetime | None
    data_origin: str | None = Field(description=ORIGINS)
    synthetic: bool
    validation_status: str
    nodata: float | None
    coverage: dict[str, Any]  # valid_percent, missing_percent, aoi_coverage_percent
    provenance: dict[str, Any]
    lineage_hash: str | None
    input_hash: str | None
    file: str | None = None  # file NAME only, never a path
    reason: str | None = None  # why a dataset is not available


class ManifestRead(BaseModel):
    area_id: uuid.UUID
    run_id: uuid.UUID | None
    generated_at: datetime
    reference_grid: dict[str, Any] | None
    entries: list[ManifestEntry]
    counts: dict[str, int]
    contains_synthetic_data: bool
    validation_status: str = "NOT_VALIDATED"
    real_data_validation: str = "NOT_PERFORMED"
    notes: list[str]
