"""Shared vocabulary for the Phase 2 data-acquisition pipeline.

Everything here is provider-neutral. Providers translate NASA/ASF responses INTO these
types; services and the API only ever see these types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shapely.geometry.base import BaseGeometry

if TYPE_CHECKING:
    from app.services.data_acquisition.aoi import AOI


class Maturity(StrEnum):
    VALIDATED = "VALIDATED"
    PROVISIONAL = "PROVISIONAL"
    BETA = "BETA"


class AcquisitionStatus(StrEnum):
    DISCOVERED = "DISCOVERED"  # metadata only; nothing downloaded
    QUEUED = "QUEUED"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"  # complete file on disk, not yet validated
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"  # file passed format-aware checks (NOT a scientific validation)
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    UNAVAILABLE = "UNAVAILABLE"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProviderName(StrEnum):
    NISAR = "NISAR"
    NASADEM = "NASADEM"
    GPM = "GPM"
    SMAP = "SMAP"
    OPERA = "OPERA"
    LANDSLIDE_CATALOG = "LANDSLIDE_CATALOG"


# ---- errors ------------------------------------------------------------------------
class DataAcquisitionError(Exception):
    """Base class. Messages must never contain credentials."""


class AuthenticationError(DataAcquisitionError):
    pass


class ProviderError(DataAcquisitionError):
    """A provider could not complete a catalog operation (network, CMR error, bad payload)."""


class DownloadError(DataAcquisitionError):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class FileValidationError(DataAcquisitionError):
    pass


class AOIError(DataAcquisitionError, ValueError):
    pass


# ---- data -------------------------------------------------------------------------
@dataclass(frozen=True)
class CollectionInfo:
    provider: ProviderName
    short_name: str  # official CMR short name, e.g. NISAR_L2_GUNW_V1
    dataset_name: str
    product_type: str  # GUNW / GCOV / DEM / IMERG_DAILY / ...
    version: str
    maturity: Maturity | None  # None where the notion does not apply (NASADEM, IMERG, ...)
    description: str = ""
    documentation_url: str | None = None
    concept_id: str | None = None  # CMR concept id, e.g. C123-ASF
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchQuery:
    aoi: AOI
    start: datetime | None = None
    end: datetime | None = None
    product_types: tuple[str, ...] = ()
    maturities: tuple[Maturity, ...] = (Maturity.VALIDATED,)
    max_results: int = 10


@dataclass
class GranuleRecord:
    """One catalog hit, normalized. A GranuleRecord is METADATA ONLY, not a downloaded file."""

    provider: ProviderName
    granule_id: str
    collection_short_name: str
    product_type: str
    version: str
    maturity: Maturity | None
    acquisition_start: datetime | None
    acquisition_end: datetime | None
    footprint: BaseGeometry | None = None  # EPSG:4326
    processing_date: datetime | None = None
    orbit_direction: str | None = None
    relative_orbit: int | None = None
    file_format: str | None = None
    file_size_bytes: int | None = None
    download_url: str | None = None
    checksum: str | None = None  # as published by the provider
    checksum_algorithm: str | None = None  # e.g. "MD5"
    crs: str = "EPSG:4326"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def temporal_baseline_days(self) -> float | None:
        """GUNW only: days between reference and secondary acquisition, when published."""
        ref = self.metadata.get("reference_start")
        sec = self.metadata.get("secondary_start")
        if isinstance(ref, datetime) and isinstance(sec, datetime):
            return abs((sec - ref).total_seconds()) / 86400
        return None



# ---- validation / download results ---------------------------------------------------
@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ValidationReport:
    """Outcome of format-aware file checks. `ok` means the FILE is structurally sound and matches
    what was requested. It does NOT mean the data are scientifically validated."""

    ok: bool
    size_bytes: int = 0
    sha256: str | None = None
    checks: list[CheckResult] = field(default_factory=list)
    extracted: dict[str, Any] = field(default_factory=dict)  # e.g. product_type, footprint_wkt, dates

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in self.checks],
            "extracted": self.extracted,
        }


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    size_bytes: int
    sha256: str
    resumed: bool = False
