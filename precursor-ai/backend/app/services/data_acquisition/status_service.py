"""Pipeline status for the dashboard and CLI. Never includes credentials."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.data_acquisition import DataAcquisition
from app.models.download_job import DownloadJob
from app.models.landslide_event import LandslideEvent
from app.schemas.data_acquisition import DataStatus
from app.services.data_acquisition.registry import provider_statuses
from app.services.data_acquisition.types import AcquisitionStatus as A, JobStatus as J

_WALK_CAP = 50_000  # shortcut: sizes beyond this many files are undercounted; replace with a DB sum if it matters


def _dir_size(root: Path) -> int | None:
    if not root.is_dir():
        return 0
    total = seen = 0
    for base, _, files in os.walk(root):
        for f in files:
            seen += 1
            if seen > _WALK_CAP:
                return total
            try:
                total += os.path.getsize(os.path.join(base, f))
            except OSError:
                pass
    return total


def compute_status(settings: Settings, auth, providers, session: Session) -> DataStatus:
    count = lambda col, *where: session.scalar(select(func.count()).select_from(col).where(*where)) or 0  # noqa: E731
    try:
        free = shutil.disk_usage(settings.data_root).free
    except OSError:
        free = None
    dist = dict(session.execute(
        select(DataAcquisition.product_type, func.count()).group_by(DataAcquisition.product_type)).all())
    return DataStatus(
        providers=provider_statuses(settings, auth, providers, session),
        earthdata_credentials_configured=auth.status() == "configured",
        acquisitions_registered=count(DataAcquisition),
        files_downloaded=count(DataAcquisition, DataAcquisition.status.in_(
            [A.DOWNLOADED.value, A.VALIDATING.value, A.VALIDATED.value])),
        files_validated=count(DataAcquisition, DataAcquisition.status == A.VALIDATED.value),
        jobs_failed=count(DownloadJob, DownloadJob.status == J.FAILED.value),
        jobs_active=count(DownloadJob, DownloadJob.status.in_([J.QUEUED.value, J.RUNNING.value])),
        landslide_events=count(LandslideEvent),
        product_distribution=dist,
        storage_free_bytes=free,
        storage_used_bytes=_dir_size(Path(settings.data_root) / "raw"),
        data_root=str(settings.data_root),
    )
