"""Request/response contract for /api/v1/data/*. Mirrored by frontend/types/data.ts."""
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Maturity = Literal["VALIDATED", "PROVISIONAL", "BETA"]
AcquisitionStatus = Literal[
    "DISCOVERED", "QUEUED", "DOWNLOADING", "DOWNLOADED", "VALIDATING", "VALIDATED", "FAILED", "SKIPPED", "UNAVAILABLE"
]
JobStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
ProviderName = Literal["NISAR", "NASADEM", "GPM", "SMAP", "OPERA", "LANDSLIDE_CATALOG"]


class CollectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: ProviderName
    collection_short_name: str
    dataset_name: str
    product_type: str
    version: str
    maturity: Maturity | None
    description: str | None
    documentation_url: str | None
    cmr_concept_id: str | None
    discovered_at: datetime


class AOIInput(BaseModel):
    """Either reference a registered monitored area, or give a GeoJSON geometry. Never both."""

    monitored_area_id: uuid.UUID | None = None
    geometry: dict[str, Any] | None = Field(default=None, description="GeoJSON Polygon/MultiPolygon, EPSG:4326")
    name: str | None = None

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.monitored_area_id is None) == (self.geometry is None):
            raise ValueError("provide exactly one of monitored_area_id or geometry")
        return self


class SearchRequest(BaseModel):
    aoi: AOIInput
    start_date: datetime | None = None
    end_date: datetime | None = None
    providers: list[Literal["NISAR", "OPERA", "NASADEM", "GPM"]] = Field(default_factory=lambda: ["NISAR"], min_length=1,
                                                                          description="Catalogs to search (metadata only). `products` and `maturities` apply to NISAR.")
    products: list[str] = Field(default_factory=lambda: ["GUNW", "GCOV", "GSLC"])
    maturities: list[Maturity] = Field(default_factory=lambda: ["VALIDATED"])
    max_results: int = Field(default=10, ge=1, le=100)
    dry_run: bool = Field(default=False, description="Search only; do not register results in the database")

    @model_validator(mode="after")
    def dates_ordered(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        return self


class GranuleResult(BaseModel):
    """A catalog hit. `registered`/`status` say whether we have recorded or downloaded it."""

    provider: ProviderName
    granule_id: str
    collection_short_name: str
    product_type: str
    version: str
    maturity: Maturity | None
    acquisition_start: datetime | None
    acquisition_end: datetime | None
    temporal_baseline_days: float | None = None
    orbit_direction: str | None = None
    relative_orbit: int | None = None
    file_format: str | None = None
    file_size_bytes: int | None = None
    footprint: dict[str, Any] | None = None  # GeoJSON
    registered: bool = False
    acquisition_id: uuid.UUID | None = None
    status: AcquisitionStatus = "DISCOVERED"
    data_kind: Literal["metadata_only", "downloaded", "validated"] = "metadata_only"


class SearchResponse(BaseModel):
    dry_run: bool
    aoi_name: str
    results: list[GranuleResult]
    warnings: list[str] = Field(default_factory=list)  # e.g. "no VALIDATED SME2 collection exists"
    provider_errors: dict[str, str] = Field(default_factory=dict)


class AcquisitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    monitored_area_id: uuid.UUID | None
    collection_id: uuid.UUID
    provider: ProviderName
    granule_id: str
    product_type: str
    acquisition_start: datetime | None
    acquisition_end: datetime | None
    processing_date: datetime | None
    orbit_direction: str | None
    relative_orbit: int | None
    footprint: dict[str, Any] | None = None
    crs: str
    file_format: str | None
    file_size_bytes: int | None
    download_url: str | None
    local_file_path: str | None
    checksum: str | None
    checksum_algorithm: str | None
    maturity: Maturity | None
    status: AcquisitionStatus
    retrieved_at: datetime | None
    metadata_json: dict[str, Any]
    validation_report: dict[str, Any]
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class AcquisitionList(BaseModel):
    items: list[AcquisitionRead]
    total: int


class DownloadCreate(BaseModel):
    """Create download jobs for granules that are already registered (from a non-dry-run search)."""

    acquisition_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class DownloadJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    acquisition_id: uuid.UUID
    status: JobStatus
    progress: float
    bytes_downloaded: int
    attempts: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    granule_id: str | None = None
    product_type: str | None = None


class DownloadCreateResponse(BaseModel):
    jobs: list[DownloadJobRead]
    skipped: dict[str, str] = Field(default_factory=dict)  # acquisition_id -> reason no job was created


class DownloadJobList(BaseModel):
    items: list[DownloadJobRead]
    total: int


class EnvironmentalAcquireRequest(BaseModel):
    aoi: AOIInput
    start_date: datetime
    end_date: datetime
    include_smap: bool = False
    dry_run: bool = True  # safe default: report what WOULD be fetched
    max_granules: int = Field(default=10, ge=1, le=200)


class EnvironmentalAcquireResponse(BaseModel):
    dry_run: bool
    results: list[GranuleResult]
    jobs: list[DownloadJobRead] = Field(default_factory=list)
    provider_errors: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class LandslideEventRead(BaseModel):
    id: uuid.UUID
    external_event_id: str
    event_date: datetime | None
    location_name: str | None
    country: str | None
    trigger: str | None
    landslide_type: str | None
    source: str | None
    longitude: float
    latitude: float
    original_attributes: dict[str, Any]
    dataset_version: str


class LandslideEventList(BaseModel):
    items: list[LandslideEventRead]
    total: int
    limitations: str


class LandslideImportRequest(BaseModel):
    """Import from the official export. `file_path` imports a local copy instead of downloading."""

    file_path: str | None = None
    force: bool = False


class LandslideImportResponse(BaseModel):
    dataset_version: str
    inserted: int
    updated: int
    skipped_invalid: int
    source_file: str
    limitations: str


class ProviderStatus(BaseModel):
    name: ProviderName
    enabled: bool
    optional: bool
    authentication: Literal["not_required", "configured", "missing", "failed"]
    collections_discovered: int
    last_successful_acquisition: datetime | None
    note: str | None = None


class DataStatus(BaseModel):
    providers: list[ProviderStatus]
    earthdata_credentials_configured: bool
    acquisitions_registered: int
    files_downloaded: int
    files_validated: int
    jobs_failed: int
    jobs_active: int
    landslide_events: int
    product_distribution: dict[str, int]
    storage_free_bytes: int | None
    storage_used_bytes: int | None
    data_root: str
