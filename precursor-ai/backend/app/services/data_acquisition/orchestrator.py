"""Download jobs: queue -> download -> file validation. Statuses only advance on real evidence:
DOWNLOADED = complete file on disk; VALIDATED = file passed format-aware checks (not a scientific validation)."""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.data_acquisition import DataAcquisition
from app.models.download_job import DownloadJob
from app.services.data_acquisition import storage
from app.services.data_acquisition.metadata_service import MetadataRegistrationService, scrub
from app.services.data_acquisition.providers.base import DataProvider
from app.services.data_acquisition.types import (
    AcquisitionStatus as A,
    AuthenticationError,
    DownloadError,
    JobStatus as J,
)

log = logging.getLogger(__name__)
_ACTIVE = (J.QUEUED.value, J.RUNNING.value)
_PROGRESS_INTERVAL_S = 0.5
AUTH_MESSAGE = "Earthdata credentials missing or invalid; set EARTHDATA_USERNAME and EARTHDATA_PASSWORD."


@dataclass
class JobPlan:
    jobs: list[DownloadJob] = field(default_factory=list)
    skipped: dict[uuid.UUID, str] = field(default_factory=dict)  # acquisition_id -> reason


def _now() -> datetime:
    return datetime.now(UTC)


class AcquisitionOrchestrator:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        providers: dict[str, DataProvider],
        validator: Any,
        settings: Settings,
        *,
        executor: Executor | None = None,
    ):
        self.session_factory = session_factory
        self.providers = providers
        self.validator = validator
        self.settings = settings
        self._executor = executor

    @property
    def executor(self) -> Executor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(self.settings.max_concurrent_downloads, thread_name_prefix="dl")
        return self._executor

    # ---- creating / retrying jobs --------------------------------------------------
    def plan_jobs(self, acquisition_ids: list[uuid.UUID]) -> JobPlan:
        plan = JobPlan()
        cap = self.settings.max_granules_per_request
        with self.session_factory() as s:
            for i, aid in enumerate(dict.fromkeys(acquisition_ids)):
                acq = s.get(DataAcquisition, aid)
                if acq is None:
                    plan.skipped[aid] = "not registered; run a (non-dry-run) search first"
                elif i >= cap:
                    plan.skipped[aid] = f"exceeds max_granules_per_request ({cap})"
                elif acq.status in (A.VALIDATED.value, A.DOWNLOADED.value):
                    plan.skipped[aid] = f"already {acq.status}"
                elif s.scalar(select(DownloadJob.id).where(
                        DownloadJob.acquisition_id == aid, DownloadJob.status.in_(_ACTIVE)).limit(1)):
                    plan.skipped[aid] = "a download job is already active"
                elif acq.file_size_bytes and acq.file_size_bytes > self.settings.max_file_size_bytes:
                    acq.status, acq.error_message = A.SKIPPED.value, "exceeds max_file_size_bytes"
                    plan.skipped[aid] = acq.error_message
                else:
                    acq.status, acq.error_message = A.QUEUED.value, None
                    job = DownloadJob(acquisition_id=aid, status=J.QUEUED.value)
                    s.add(job)
                    plan.jobs.append(job)
            s.commit()
        for job in plan.jobs:
            self.executor.submit(self.run_job, job.id)  # returns immediately; callers are never blocked
        return plan

    def create_jobs(self, acquisition_ids: list[uuid.UUID]) -> list[DownloadJob]:
        return self.plan_jobs(acquisition_ids).jobs

    def retry_job(self, job_id: uuid.UUID) -> DownloadJob:
        with self.session_factory() as s:
            job = s.get(DownloadJob, job_id)
            if job is None:
                raise LookupError("job not found")
            if job.status != J.FAILED.value:
                raise ValueError(f"only FAILED jobs can be retried (job is {job.status})")
            job.status, job.error_message, job.completed_at = J.QUEUED.value, None, None
            job.acquisition.status, job.acquisition.error_message = A.QUEUED.value, None
            s.commit()
        self.executor.submit(self.run_job, job_id)
        return job

    # ---- the worker ----------------------------------------------------------------
    def run_job(self, job_id: uuid.UUID) -> None:
        """Runs in a worker thread with its own session; never raises."""
        try:
            self._run(job_id)
        except Exception as exc:
            log.exception("job %s crashed", job_id)
            self._fail(job_id, f"unexpected {type(exc).__name__}: {scrub(exc, self.settings)}")

    def _fail(self, job_id: uuid.UUID, message: str) -> None:
        with self.session_factory() as s:
            job = s.get(DownloadJob, job_id)
            if job is None:
                return
            job.status, job.error_message, job.completed_at = J.FAILED.value, message, _now()
            job.acquisition.status, job.acquisition.error_message = A.FAILED.value, message
            s.commit()

    def _run(self, job_id: uuid.UUID) -> None:
        with self.session_factory() as s:
            job = s.get(DownloadJob, job_id)
            if job is None:
                return
            acq = job.acquisition
            svc = MetadataRegistrationService(s)
            provider = self.providers.get(acq.provider)
            if provider is None:
                return self._fail(job_id, f"provider {acq.provider} is not enabled")
            job.status, job.attempts, job.started_at = J.RUNNING.value, job.attempts + 1, _now()
            job.progress, job.bytes_downloaded, job.error_message, job.completed_at = 0.0, 0, None, None
            svc.set_status(acq, A.DOWNLOADING)

            granule = svc.to_record(acq)
            total_hint = acq.file_size_bytes
            last = [0.0]

            def progress(done: int, total: int | None) -> None:
                now = time.monotonic()
                total = total or total_hint
                if now - last[0] < _PROGRESS_INTERVAL_S and not (total and done >= total):
                    return
                last[0] = now
                job.bytes_downloaded = done
                if total:
                    job.progress = min(done / total, 1.0)
                s.commit()

            try:
                path = provider.download_granule(
                    granule, storage.provider_dir(self.settings.data_root, granule), progress=progress)
            except AuthenticationError:
                return self._fail(job_id, AUTH_MESSAGE)
            except DownloadError as exc:
                return self._fail(job_id, f"download failed: {scrub(exc, self.settings)}")

            size = Path(path).stat().st_size
            job.bytes_downloaded = size
            svc.mark_downloaded(acq, path, None, size)
            if not self._validate(s, svc, acq):
                return self._fail(job_id, acq.error_message or "file validation failed")
            job.status, job.progress, job.completed_at = J.COMPLETED.value, 1.0, _now()
            s.commit()
            self._manifest(svc, acq)

    def _manifest(self, svc: MetadataRegistrationService, acq: DataAcquisition) -> None:
        try:
            svc.write_manifest(acq, self.settings.data_root)
        except Exception:  # provenance is best effort; the file and DB row are already correct
            log.warning("manifest write failed for %s", acq.granule_id, exc_info=True)

    def _validate(self, s: Session, svc: MetadataRegistrationService, acq: DataAcquisition) -> bool:
        svc.set_status(acq, A.VALIDATING)
        pub = (acq.metadata_json or {}).get("published_checksum") or {}
        try:
            report = self.validator.validate(
                Path(acq.local_file_path), svc.to_record(acq),
                expected_checksum=pub.get("value"), expected_checksum_algorithm=pub.get("algorithm"),
            )
        except Exception as exc:
            report = None
            acq.error_message = f"validation error: {type(exc).__name__}: {scrub(exc, self.settings)}"
        if report is not None and report.ok:
            acq.validation_report = report.as_dict()
            if report.sha256:
                acq.checksum, acq.checksum_algorithm = report.sha256, "SHA-256"
            acq.status, acq.error_message = A.VALIDATED.value, None
        else:
            if report is not None:
                acq.validation_report = report.as_dict()
                bad = "; ".join(f"{c.name}: {c.detail}" for c in report.checks if not c.passed)
                acq.error_message = f"file validation failed: {bad or 'unspecified'}"
            acq.status = A.FAILED.value
        s.commit()
        return acq.status == A.VALIDATED.value

    # ---- maintenance ---------------------------------------------------------------
    def revalidate(self, acquisition_id: uuid.UUID) -> DataAcquisition:
        with self.session_factory() as s:
            acq = s.get(DataAcquisition, acquisition_id)
            if acq is None:
                raise LookupError("acquisition not found")
            if not acq.local_file_path or not Path(acq.local_file_path).is_file():
                raise ValueError("no local file to validate")
            svc = MetadataRegistrationService(s)
            if self._validate(s, svc, acq):
                self._manifest(svc, acq)
            return acq

    def recover_stale_jobs(self) -> int:
        """Call at startup: nothing is running in a fresh process, so RUNNING/QUEUED jobs were interrupted."""
        msg = "interrupted by restart; retry to resume"
        with self.session_factory() as s:
            jobs = list(s.scalars(select(DownloadJob).where(DownloadJob.status.in_(_ACTIVE))))
            for job in jobs:
                job.status, job.error_message, job.completed_at = J.FAILED.value, msg, _now()
                if job.acquisition.status in (A.QUEUED.value, A.DOWNLOADING.value, A.VALIDATING.value):
                    job.acquisition.status, job.acquisition.error_message = A.FAILED.value, msg
            s.commit()
            return len(jobs)
