"""Environmental layers (NASADEM terrain, GPM rainfall, optional SMAP) for an AOI and date range."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.core.config import Settings
from app.models.download_job import DownloadJob
from app.schemas.data_acquisition import GranuleResult
from app.services.data_acquisition.aoi import AOI
from app.services.data_acquisition.orchestrator import AcquisitionOrchestrator
from app.services.data_acquisition.search_service import AcquisitionSearchService
from app.services.data_acquisition.types import SearchQuery


@dataclass
class EnvironmentalOutcome:
    results: list[GranuleResult] = field(default_factory=list)
    jobs: list[DownloadJob] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provider_errors: dict[str, str] = field(default_factory=dict)


def acquire_environmental(
    search: AcquisitionSearchService, orchestrator: AcquisitionOrchestrator, settings: Settings, aoi: AOI,
    start: datetime, end: datetime, *, include_smap: bool = False, dry_run: bool = True,
    max_granules: int = 10, monitored_area_id: UUID | None = None,
) -> EnvironmentalOutcome:
    names = ["NASADEM", "GPM"]
    out = EnvironmentalOutcome()
    if include_smap:
        if settings.enable_smap:
            names.append("SMAP")
        else:
            out.warnings.append("SMAP requested but disabled (ENABLE_SMAP=false); skipped")
    found = search.search(
        SearchQuery(aoi=aoi, start=start, end=end, max_results=max_granules),
        provider_names=names, register=not dry_run, monitored_area_id=monitored_area_id)
    out.results = found.results[:max_granules]
    out.warnings += found.warnings
    out.provider_errors = found.provider_errors
    days = (end - start).days + 1
    if settings.gpm_resolution == "daily" and days > max_granules:
        out.warnings.append(
            f"GPM IMERG daily is one global file per day: {days} days need {days} files but at most "
            f"{max_granules} are returned; shorten the date range or raise max_granules.")
    if not dry_run:
        ids = [r.acquisition_id for r in out.results if r.acquisition_id]
        plan = orchestrator.plan_jobs(ids)
        out.jobs = plan.jobs
        out.warnings += [f"{aid}: not queued ({why})" for aid, why in plan.skipped.items()]
    return out
