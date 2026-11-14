"""Shared vocabulary for Phase 4 (environmental and geospatial integration). Pure data; no I/O.

Scientific rules encoded here:
* Every layer says WHERE it came from (`DataOrigin`) and WHAT KIND of number it is (`MeasurementKind`).
* `ValidationStatus` is never "validated" in Phase 4: file integrity and processing success are not scientific validation.
* There is deliberately no ML/prediction kind that any code can produce; `ML_PREDICTION` exists only to document
  what must never be written by this layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

# Re-use the Phase 3 origin labels so synthetic/real/unverified mean the same thing everywhere.
from app.services.insar.types import DataOrigin

__all__ = [
    "DataOrigin", "LayerKind", "MeasurementKind", "LayerStatus", "ValidationStatus", "RunStatus", "StageName",
    "StageStatus", "TemporalKind", "TEMPORAL_OF", "RASTER_KINDS", "SERIES_KINDS", "VECTOR_KINDS", "CATEGORICAL_KINDS", "Provenance", "LayerQuality", "SYNTHETIC_TAG", "EnvError", "NotAvailable", "FEATURE_GROUPS",
]

# Raster/HDF5 tag or attribute that marks a file produced by this repository's test/demo generators.
SYNTHETIC_TAG = "PRECURSOR_SYNTHETIC_FIXTURE"


class LayerKind(StrEnum):
    ELEVATION = "ELEVATION"
    SLOPE = "SLOPE"
    ASPECT = "ASPECT"
    RAINFALL = "RAINFALL"  # aggregated series (daily/monthly/rolling); not a raster
    SOIL = "SOIL"
    LAND_COVER = "LAND_COVER"
    HISTORICAL_LANDSLIDES = "HISTORICAL_LANDSLIDES"  # vector, from the Phase 2 catalog (reference only)
    SEISMIC = "SEISMIC"  # vector, USGS catalog
    INSAR_DISPLACEMENT = "INSAR_DISPLACEMENT"  # reference to a Phase 3 product, never copied or reinterpreted
    INSAR_COHERENCE = "INSAR_COHERENCE"
    INSAR_VELOCITY = "INSAR_VELOCITY"
    SMAP_SOIL_MOISTURE = "SMAP_SOIL_MOISTURE"  # series (AOI statistic over time), not a raster here
    LITHOLOGY = "LITHOLOGY"  # categorical raster from user-provided geology (class ids + source legend preserved)
    NDVI = "NDVI"  # raster from a user-provided NDVI / vegetation-index file
    DISTANCE_RIVER = "DISTANCE_RIVER"  # metres, from user-provided vectors, on the reference grid
    DISTANCE_FAULT = "DISTANCE_FAULT"
    DISTANCE_ROAD = "DISTANCE_ROAD"


RASTER_KINDS = {LayerKind.ELEVATION, LayerKind.SLOPE, LayerKind.ASPECT, LayerKind.SOIL, LayerKind.LAND_COVER,
                LayerKind.INSAR_DISPLACEMENT, LayerKind.INSAR_COHERENCE, LayerKind.INSAR_VELOCITY,
                LayerKind.LITHOLOGY, LayerKind.NDVI, LayerKind.DISTANCE_RIVER, LayerKind.DISTANCE_FAULT, LayerKind.DISTANCE_ROAD}
SERIES_KINDS = {LayerKind.RAINFALL, LayerKind.SMAP_SOIL_MOISTURE}  # time series of an AOI statistic (no raster)
VECTOR_KINDS = {LayerKind.HISTORICAL_LANDSLIDES, LayerKind.SEISMIC}
CATEGORICAL_KINDS = {LayerKind.LAND_COVER, LayerKind.LITHOLOGY}  # nearest-neighbour only; class ids never interpolated or averaged
CIRCULAR_KINDS = {LayerKind.ASPECT}  # degrees 0-360: never arithmetically averaged across 0/360

FEATURE_GROUPS = ("terrain", "rainfall", "smap", "soil", "land_cover", "lithology", "vegetation", "distances",
                  "historical_landslides", "seismic", "insar")


class TemporalKind(StrEnum):
    """Does the layer describe a fixed property (static) or something that varies in time (dynamic)? Stack metadata only."""

    STATIC = "static"
    DYNAMIC = "dynamic"


TEMPORAL_OF = {
    LayerKind.ELEVATION: TemporalKind.STATIC, LayerKind.SLOPE: TemporalKind.STATIC, LayerKind.ASPECT: TemporalKind.STATIC,
    LayerKind.SOIL: TemporalKind.STATIC, LayerKind.LAND_COVER: TemporalKind.STATIC, LayerKind.LITHOLOGY: TemporalKind.STATIC,
    LayerKind.DISTANCE_RIVER: TemporalKind.STATIC, LayerKind.DISTANCE_FAULT: TemporalKind.STATIC,
    LayerKind.DISTANCE_ROAD: TemporalKind.STATIC, LayerKind.HISTORICAL_LANDSLIDES: TemporalKind.STATIC,
    LayerKind.RAINFALL: TemporalKind.DYNAMIC, LayerKind.SMAP_SOIL_MOISTURE: TemporalKind.DYNAMIC, LayerKind.NDVI: TemporalKind.DYNAMIC,
    LayerKind.SEISMIC: TemporalKind.DYNAMIC, LayerKind.INSAR_DISPLACEMENT: TemporalKind.DYNAMIC,
    LayerKind.INSAR_COHERENCE: TemporalKind.DYNAMIC, LayerKind.INSAR_VELOCITY: TemporalKind.DYNAMIC,
}


class MeasurementKind(StrEnum):
    SOURCE_OBSERVATION = "SOURCE_OBSERVATION"  # value as delivered by the provider
    DERIVED_MEASUREMENT = "DERIVED_MEASUREMENT"  # computed from observations (slope, aspect, accumulations)
    STATISTICAL_SUMMARY = "STATISTICAL_SUMMARY"  # descriptive statistics of the above over an AOI
    ML_PREDICTION = "ML_PREDICTION"  # RESERVED. Must never be produced before an authorized ML phase.


class LayerStatus(StrEnum):
    SOURCE_DISCOVERED = "SOURCE_DISCOVERED"  # a catalog says it exists; no file
    SOURCE_AVAILABLE = "SOURCE_AVAILABLE"  # a local file/record exists
    DOWNLOADED = "DOWNLOADED"
    INTEGRITY_CHECKED = "INTEGRITY_CHECKED"
    PROCESSED = "PROCESSED"
    PARTIALLY_PROCESSED = "PARTIALLY_PROCESSED"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    FAILED = "FAILED"


class ValidationStatus(StrEnum):
    NOT_VALIDATED = "NOT_VALIDATED"  # the only value Phase 4 writes


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"  # every requested stage finished
    PARTIAL = "PARTIAL"  # some stages finished, others had no input or failed (never a silent pass)
    FAILED = "FAILED"  # nothing useful was produced
    CANCELLED = "CANCELLED"


class StageName(StrEnum):
    DEM = "DEM"
    TERRAIN = "TERRAIN"
    RAINFALL = "RAINFALL"
    SMAP = "SMAP"
    SOIL = "SOIL"
    LAND_COVER = "LAND_COVER"
    LITHOLOGY = "LITHOLOGY"
    NDVI = "NDVI"
    DISTANCES = "DISTANCES"
    HISTORICAL_LANDSLIDES = "HISTORICAL_LANDSLIDES"
    SEISMIC = "SEISMIC"
    INSAR = "INSAR"
    REFERENCE_GRID = "REFERENCE_GRID"  # chooses the common metric grid and aligns every raster layer to it
    FEATURES = "FEATURES"
    MANIFEST = "MANIFEST"  # writes the stack manifest
    QUALITY = "QUALITY"


class StageStatus(StrEnum):
    DONE = "DONE"
    PARTIAL = "PARTIAL"
    NOT_AVAILABLE = "NOT_AVAILABLE"  # no input exists: reported, never filled
    SKIPPED = "SKIPPED"  # already done for identical inputs (retry without redoing work)
    FAILED = "FAILED"


class EnvError(Exception):
    """A scientific or data check failed; the stage must stop and report it."""


class NotAvailable(Exception):
    """The input for a stage does not exist. The stage ends NOT_AVAILABLE; the run continues."""


@dataclass
class Provenance:
    """Where a layer or feature came from. Stored with every layer and feature (JSONB)."""

    provider: str  # NASADEM | GPM | SOILGRIDS | WORLDCOVER | USGS | NASA_GLC | INSAR_PHASE3 | ...
    dataset_name: str
    dataset_version: str | None = None
    origin: DataOrigin = DataOrigin.LOCAL_UNVERIFIED
    measurement_kind: MeasurementKind = MeasurementKind.SOURCE_OBSERVATION
    acquisition_ids: list[str] = field(default_factory=list)  # Phase 2 data_acquisitions ids
    source_files: list[str] = field(default_factory=list)  # file NAMES only, never absolute paths
    insar_run_id: str | None = None
    observation_start: datetime | None = None
    observation_end: datetime | None = None
    units: str | None = None
    method: str | None = None
    nodata: float | None = None
    validation_status: ValidationStatus = ValidationStatus.NOT_VALIDATED
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        for k in ("origin", "measurement_kind", "validation_status"):
            d[k] = d[k].value
        for k in ("observation_start", "observation_end"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


@dataclass
class LayerQuality:
    """Per-layer quality figures. Percentages are 0-100. `None` = not applicable/unknown, never zero."""

    total_pixels: int | None = None
    valid_pixels: int | None = None
    valid_percent: float | None = None
    missing_percent: float | None = None
    aoi_coverage_percent: float | None = None  # how much of the AOI the source actually covers
    native_resolution: dict[str, Any] | None = None  # {"x":..,"y":..,"unit":"degree|metre"}
    processing_resolution: dict[str, Any] | None = None
    crs: str | None = None
    temporal_start: str | None = None
    temporal_end: str | None = None
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}
