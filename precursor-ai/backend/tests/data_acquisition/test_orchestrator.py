import pytest
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.models.data_acquisition import DataAcquisition
from app.models.download_job import DownloadJob
from app.services.data_acquisition.metadata_service import MetadataRegistrationService
from app.services.data_acquisition.orchestrator import AUTH_MESSAGE, AcquisitionOrchestrator
from app.services.data_acquisition.types import (
    AcquisitionStatus as A,
    AuthenticationError,
    CollectionInfo,
    DownloadError,
    Maturity,
    ProviderName,
)
from tests.data_acquisition.fakes import FakeProvider, FakeValidator, SyncExecutor, make_record


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def acq_id(db):
    svc = MetadataRegistrationService(db)
    col = svc.upsert_collection(CollectionInfo(ProviderName.NISAR, "FAKE_COLL", "Fake", "GUNW", "1", Maturity.VALIDATED))
    acq, _ = svc.register_granule(make_record(size=10), col)
    return acq.id


def _orch(factory, tmp_path, provider=None, validator=None, **settings):
    s = Settings(data_root=tmp_path, **settings)
    return AcquisitionOrchestrator(
        factory, {"NISAR": provider or FakeProvider()}, validator or FakeValidator(), s, executor=SyncExecutor()
    )


def _state(factory, acq_id, job_id=None):
    with factory() as s:
        acq = s.get(DataAcquisition, acq_id)
        job = s.get(DownloadJob, job_id) if job_id else None
        return acq, job


def test_end_to_end_success(factory, acq_id, tmp_path):
    prov, val = FakeProvider(), FakeValidator()
    orch = _orch(factory, tmp_path, prov, val)
    [job] = orch.create_jobs([acq_id])
    acq, job = _state(factory, acq_id, job.id)
    assert acq.status == "VALIDATED" and job.status == "COMPLETED"
    assert job.progress == 1.0 and job.bytes_downloaded == 10 and job.attempts == 1 and job.completed_at
    assert acq.checksum == "f" * 64 and acq.checksum_algorithm == "SHA-256" and acq.retrieved_at
    assert acq.validation_report["ok"] is True
    assert val.calls[0][1] == "abc"  # the provider-published checksum is what the file is checked against
    assert (tmp_path / "metadata" / "acquisitions" / "G1.json").exists()
    assert "raw" in acq.local_file_path.replace("\\", "/")


def test_status_sequence_is_honest(factory, acq_id, tmp_path):
    seen = []

    class Spy(FakeValidator):
        def validate(self, path, granule, **kw):
            seen.append(_state(factory, acq_id)[0].status)  # file on disk, not yet validated
            return super().validate(path, granule, **kw)

    class SpyProv(FakeProvider):
        def download_granule(self, granule, dest_dir, *, progress=None):
            seen.append(_state(factory, acq_id)[0].status)
            return super().download_granule(granule, dest_dir, progress=progress)

    _orch(factory, tmp_path, SpyProv(), Spy()).create_jobs([acq_id])
    assert seen == ["DOWNLOADING", "VALIDATING"]


def test_validation_failure_marks_failed_not_completed(factory, acq_id, tmp_path):
    orch = _orch(factory, tmp_path, validator=FakeValidator(ok=False))
    [job] = orch.create_jobs([acq_id])
    acq, job = _state(factory, acq_id, job.id)
    assert acq.status == "FAILED" and job.status == "FAILED"
    assert "not an HDF5 file" in acq.error_message and acq.local_file_path  # file kept for inspection
    assert job.completed_at is not None


def test_download_error_then_retry(factory, acq_id, tmp_path):
    prov = FakeProvider(download_error=DownloadError("net down https://h/f?token=SECRET"))
    orch = _orch(factory, tmp_path, prov)
    [job] = orch.create_jobs([acq_id])
    acq, j = _state(factory, acq_id, job.id)
    assert acq.status == "FAILED" and j.status == "FAILED" and "SECRET" not in j.error_message
    prov.download_error = None
    orch.retry_job(job.id)
    acq, j = _state(factory, acq_id, job.id)
    assert acq.status == "VALIDATED" and j.status == "COMPLETED" and j.attempts == 1  # a retry starts a fresh attempt series (Phase 2 issue 7, fixed in Phase 10)
    with pytest.raises(ValueError):
        orch.retry_job(job.id)  # only FAILED jobs


def test_auth_and_unexpected_errors(factory, acq_id, tmp_path):
    prov = FakeProvider(download_error=AuthenticationError("401 for user bob"))
    orch = _orch(factory, tmp_path, prov)
    [job] = orch.create_jobs([acq_id])
    assert _state(factory, acq_id, job.id)[1].error_message == AUTH_MESSAGE
    prov.download_error = RuntimeError("weird")
    orch.retry_job(job.id)  # must not raise out of the worker
    acq, j = _state(factory, acq_id, job.id)
    assert j.status == "FAILED" and "RuntimeError" in j.error_message and acq.status == "FAILED"


def test_skips_validated_active_and_oversize(factory, acq_id, tmp_path, db):
    orch = _orch(factory, tmp_path)
    orch.create_jobs([acq_id])
    plan = orch.plan_jobs([acq_id])
    assert plan.jobs == [] and "VALIDATED" in plan.skipped[acq_id]

    with factory() as s:  # duplicate prevention while a job is active
        s.get(DataAcquisition, acq_id).status = "FAILED"
        s.add(DownloadJob(acquisition_id=acq_id, status="RUNNING"))
        s.commit()
    assert "active" in orch.plan_jobs([acq_id]).skipped[acq_id]

    svc = MetadataRegistrationService(db)
    col = svc.upsert_collection(CollectionInfo(ProviderName.NISAR, "FAKE_COLL", "Fake", "GUNW", "1", Maturity.VALIDATED))
    big, _ = svc.register_granule(make_record("BIG", size=2000), col)
    plan = _orch(factory, tmp_path, max_file_size_bytes=1000).plan_jobs([big.id])
    assert plan.skipped[big.id] == "exceeds max_file_size_bytes"
    assert _state(factory, big.id)[0].status == "SKIPPED"


def test_stale_job_recovery_then_resume(factory, acq_id, tmp_path):
    with factory() as s:
        s.get(DataAcquisition, acq_id).status = "DOWNLOADING"
        job = DownloadJob(acquisition_id=acq_id, status="RUNNING")
        s.add(job)
        s.commit()
        job_id = job.id
    orch = _orch(factory, tmp_path)
    assert orch.recover_stale_jobs() == 1
    acq, job = _state(factory, acq_id, job_id)
    assert job.status == "FAILED" and "interrupted by restart" in job.error_message and acq.status == "FAILED"
    orch.retry_job(job_id)
    assert _state(factory, acq_id)[0].status == "VALIDATED"


def test_revalidate(factory, acq_id, tmp_path):
    val = FakeValidator(ok=False)
    orch = _orch(factory, tmp_path, validator=val)
    orch.create_jobs([acq_id])
    assert _state(factory, acq_id)[0].status == "FAILED"
    val.ok = True
    assert orch.revalidate(acq_id).status == "VALIDATED"
    val.raises = RuntimeError("x")
    assert orch.revalidate(acq_id).status == "FAILED"


def test_revalidate_without_file_refuses(factory, acq_id, tmp_path):
    with pytest.raises(ValueError):
        _orch(factory, tmp_path).revalidate(acq_id)
