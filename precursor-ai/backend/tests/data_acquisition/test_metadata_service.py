import json
from datetime import UTC, datetime

from geoalchemy2.shape import to_shape
from sqlalchemy import func, select

from app.models.data_acquisition import DataAcquisition
from app.services.data_acquisition.metadata_service import MetadataRegistrationService, scrub
from app.services.data_acquisition.types import AcquisitionStatus as A
from app.services.data_acquisition.types import CollectionInfo, Maturity, ProviderName
from tests.data_acquisition.fakes import make_record


def _col(svc):
    return svc.upsert_collection(CollectionInfo(ProviderName.NISAR, "FAKE_COLL", "Fake", "GUNW", "1", Maturity.VALIDATED))


def test_upsert_collection_updates_in_place(db):
    svc = MetadataRegistrationService(db)
    a = _col(svc)
    b = svc.upsert_collection(CollectionInfo(ProviderName.NISAR, "FAKE_COLL", "Renamed", "GUNW", "1", Maturity.VALIDATED, "d"))
    assert a.id == b.id and b.dataset_name == "Renamed" and b.description == "d"


def test_register_is_idempotent_and_stores_footprint(db):
    svc = MetadataRegistrationService(db)
    col = _col(svc)
    acq, created = svc.register_granule(make_record(), col)
    again, created2 = svc.register_granule(make_record(size=99), col)
    assert created and not created2 and acq.id == again.id
    assert db.scalar(select(func.count()).select_from(DataAcquisition)) == 1
    assert again.file_size_bytes == 99  # DISCOVERED rows get refreshed catalog metadata
    assert to_shape(again.spatial_footprint).bounds == (44.0, 40.0, 44.1, 40.1)
    assert again.metadata_json["reference_start"].startswith("2026-01-01")  # JSON-safe datetimes
    assert again.status == "DISCOVERED" and again.maturity == "VALIDATED"


def test_register_never_downgrades_or_overwrites_advanced_rows(db):
    svc = MetadataRegistrationService(db)
    col = _col(svc)
    acq, _ = svc.register_granule(make_record(), col)
    svc.mark_downloaded(acq, "/x/g.h5", "a" * 64, 10)
    svc.set_status(acq, A.VALIDATED)
    again, created = svc.register_granule(make_record(size=555), col)
    assert not created and again.status == "VALIDATED"
    assert again.file_size_bytes == 10 and again.checksum == "a" * 64 and again.checksum_algorithm == "SHA-256"
    assert again.retrieved_at is not None


def test_to_granule_result_data_kind(db):
    svc = MetadataRegistrationService(db)
    rec = make_record()
    fresh = svc.to_granule_result(rec)
    assert fresh.data_kind == "metadata_only" and not fresh.registered and fresh.temporal_baseline_days == 12
    assert fresh.footprint["type"] == "Polygon"
    acq, _ = svc.register_granule(rec, _col(svc))
    assert svc.to_granule_result(acq).data_kind == "metadata_only"
    svc.mark_downloaded(acq, "/x", None, 1)
    assert svc.to_granule_result(acq).data_kind == "downloaded"
    svc.set_status(acq, A.VALIDATED)
    r = svc.to_granule_result(acq)
    assert r.data_kind == "validated" and r.registered and r.temporal_baseline_days == 12


def test_manifest_has_no_secrets(db, tmp_path):
    svc = MetadataRegistrationService(db)
    acq, _ = svc.register_granule(make_record(), _col(svc))
    path = svc.write_manifest(acq, tmp_path)
    text = path.read_text()
    assert "SECRET" not in text and "token" not in text
    assert json.loads(text)["source_url"] == "https://example.invalid/g.h5"
    assert (tmp_path / "metadata" / "collections" / "FAKE_COLL.json").exists()


def test_list_acquisitions_filters(db):
    svc = MetadataRegistrationService(db)
    col = _col(svc)
    svc.register_granule(make_record("A", day=1), col)
    svc.register_granule(make_record("B", Maturity.BETA, day=2), col)
    rows, total = svc.list_acquisitions(maturity="BETA")
    assert total == 1 and rows[0].granule_id == "B"
    rows, total = svc.list_acquisitions(start=datetime(2026, 1, 2, tzinfo=UTC), limit=1)
    assert total == 1


def test_scrub_removes_query_strings():
    assert "SECRET" not in scrub("failed https://h/x.h5?token=SECRET now")
