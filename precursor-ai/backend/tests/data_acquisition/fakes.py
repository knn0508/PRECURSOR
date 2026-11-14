"""Test doubles: no network, no real NASA data. Everything here is synthetic."""
from __future__ import annotations

from concurrent.futures import Executor, Future
from datetime import UTC, datetime
from pathlib import Path

from shapely.geometry import box

from app.services.data_acquisition.providers.base import DataProvider
from app.services.data_acquisition.types import (
    CheckResult,
    CollectionInfo,
    GranuleRecord,
    Maturity,
    ProviderName,
    ValidationReport,
)


class SyncExecutor(Executor):
    def submit(self, fn, /, *args, **kwargs):
        fut: Future = Future()
        fut.set_result(fn(*args, **kwargs))
        return fut


def make_record(gid="G1", maturity=Maturity.VALIDATED, size=10, day=1, provider=ProviderName.NISAR, **kw) -> GranuleRecord:
    return GranuleRecord(
        provider=provider, granule_id=gid, collection_short_name="FAKE_COLL", product_type="GUNW", version="1",
        maturity=maturity, acquisition_start=datetime(2026, 1, day, tzinfo=UTC), acquisition_end=None,
        footprint=box(44.0, 40.0, 44.1, 40.1), file_format="HDF5", file_size_bytes=size,
        download_url="https://example.invalid/g.h5?token=SECRET", checksum="abc", checksum_algorithm="MD5",
        metadata={"reference_start": datetime(2026, 1, 1, tzinfo=UTC), "secondary_start": datetime(2026, 1, 13, tzinfo=UTC)},
        **kw,
    )


class FakeProvider(DataProvider):
    requires_auth_for_download = True

    def __init__(self, name=ProviderName.NISAR, records=None, fail_search=None, download_error=None, content=b"0123456789"):
        super().__init__()
        self.name = name
        self.records = records or []
        self.fail_search = fail_search
        self.download_error = download_error
        self.content = content
        self.downloads = 0

    def search_collections(self):
        if self.fail_search:
            raise self.fail_search
        return [CollectionInfo(self.name, "FAKE_COLL", "Fake", "GUNW", "1", Maturity.VALIDATED)]

    def search_granules(self, query):
        self.last_warnings = ["fake warning"]
        if self.fail_search:
            raise self.fail_search
        return list(self.records)

    def get_granule_metadata(self, granule_id):
        return next((r for r in self.records if r.granule_id == granule_id), None)

    def download_granule(self, granule, dest_dir: Path, *, progress=None) -> Path:
        self.downloads += 1
        if self.download_error:
            raise self.download_error
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{granule.granule_id}.h5"
        half = len(self.content) // 2
        path.write_bytes(self.content[:half])
        progress and progress(half, len(self.content))
        path.write_bytes(self.content)
        progress and progress(len(self.content), len(self.content))
        return path


class FakeValidator:
    def __init__(self, ok=True, raises=None):
        self.ok, self.raises, self.calls = ok, raises, []

    def validate(self, path, granule, *, expected_checksum=None, expected_checksum_algorithm=None):
        self.calls.append((path, expected_checksum))
        if self.raises:
            raise self.raises
        return ValidationReport(
            ok=self.ok, size_bytes=path.stat().st_size, sha256="f" * 64,
            checks=[CheckResult("opens_as_hdf5", self.ok, "" if self.ok else "not an HDF5 file")],
        )


class FakeDownloadManager:
    """Placeholder for providers that need one; the fake provider never uses it."""
