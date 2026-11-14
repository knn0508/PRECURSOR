"""API tests: FastAPI TestClient + dependency_overrides with fakes. No network, no real NASA data."""
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.api.v1.data import deps
from app.core.config import Settings, get_settings
from app.main import app
from app.models import DataAcquisition, DownloadJob, LandslideEvent
from app.services.data_acquisition.authentication import EarthdataAuthenticationService
from app.services.data_acquisition.metadata_service import MetadataRegistrationService
from app.services.data_acquisition.orchestrator import AcquisitionOrchestrator
from app.services.data_acquisition.providers import landslide_catalog as lc
from app.services.data_acquisition.search_service import AcquisitionSearchService
from app.services.data_acquisition.types import CollectionInfo, DownloadError, Maturity, ProviderName
from tests.data_acquisition.fakes import FakeProvider, FakeValidator, SyncExecutor, make_record
from tests.data_acquisition.test_landslide_catalog import write_csv

BASE = "/api/v1/data"
SECRETS = ("fake-user-4711", "fake-pass-0815")
DATES = {"start_date": "2026-01-01T00:00:00Z", "end_date": "2026-01-10T00:00:00Z"}


@pytest.fixture
def wire(client, db, engine, tmp_path):
    """wire(providers, **settings) overrides every /data dependency with fakes and returns the wiring."""

    def _wire(providers, validator=None, **kw):
        settings = Settings(**{
            "data_root": tmp_path, "allowed_maturities": "VALIDATED,PROVISIONAL,BETA",
            "earthdata_username": SECRETS[0], "earthdata_password": SECRETS[1], **kw})
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        orch = AcquisitionOrchestrator(factory, providers, validator or FakeValidator(), settings, executor=SyncExecutor())
        app.dependency_overrides.update({
            get_settings: lambda: settings,
            deps.get_providers: lambda: providers,
            deps.get_search_service: lambda: AcquisitionSearchService(providers, db, settings),
            deps.get_orchestrator: lambda: orch,
            deps.get_auth: lambda: EarthdataAuthenticationService(settings, login_fn=lambda s: True),
        })
        return orch

    return _wire


def aoi(polygon):
    return {"geometry": polygon}


def n(db, model):
    return db.scalar(select(func.count()).select_from(model))


def register(db, *records):
    svc = MetadataRegistrationService(db)
    col = svc.upsert_collection(CollectionInfo(ProviderName.NISAR, "FAKE_COLL", "Fake", "GUNW", "1", Maturity.VALIDATED))
    return [svc.register_granule(r, col)[0] for r in records]


# ---- collections -----------------------------------------------------------------------
def test_collections_list_filter_detail_404(client, db, wire):
    wire({"NISAR": FakeProvider()})
    svc = MetadataRegistrationService(db)
    c = svc.upsert_collection(CollectionInfo(ProviderName.NISAR, "N_COLL", "Nisar", "GUNW", "1", Maturity.VALIDATED))
    svc.upsert_collection(CollectionInfo(ProviderName.GPM, "G_COLL", "Gpm", "IMERG_DAILY", "07", None))
    assert len(client.get(f"{BASE}/collections").json()) == 2
    only = client.get(f"{BASE}/collections", params={"provider": "gpm"}).json()
    assert [x["collection_short_name"] for x in only] == ["G_COLL"]
    assert client.get(f"{BASE}/collections/{c.id}").json()["maturity"] == "VALIDATED"
    r = client.get(f"{BASE}/collections/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_collections_refresh_discovers(client, db, wire):
    wire({"NISAR": FakeProvider()})
    assert client.get(f"{BASE}/collections").json() == []
    got = client.get(f"{BASE}/collections", params={"refresh": "true"}).json()
    assert [c["collection_short_name"] for c in got] == ["FAKE_COLL"]


# ---- search ----------------------------------------------------------------------------
def test_search_dry_run_writes_nothing_then_registers(client, db, wire, polygon):
    wire({"NISAR": FakeProvider(records=[make_record("A")])})
    body = {"aoi": aoi(polygon), **DATES, "dry_run": True}
    r = client.post(f"{BASE}/search", json=body)
    assert r.status_code == 200
    assert r.json()["dry_run"] is True and r.json()["results"][0]["registered"] is False
    assert r.json()["warnings"] == ["NISAR: fake warning"]
    assert n(db, DataAcquisition) == 0
    r = client.post(f"{BASE}/search", json={**body, "dry_run": False})
    hit = r.json()["results"][0]
    assert hit["registered"] and hit["status"] == "DISCOVERED" and hit["data_kind"] == "metadata_only"
    assert hit["footprint"]["type"] == "Polygon" and n(db, DataAcquisition) == 1


def test_search_validation_errors(client, wire, polygon):
    wire({"NISAR": FakeProvider(records=[make_record("A")])}, )
    big = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}
    r = client.post(f"{BASE}/search", json={"aoi": aoi(big), "dry_run": True})
    assert r.status_code == 422 and "limit" in r.json()["error"]["message"]
    r = client.post(f"{BASE}/search", json={"aoi": aoi({"type": "Point", "coordinates": [1, 2]})})
    assert r.status_code == 422
    r = client.post(f"{BASE}/search", json={"aoi": aoi(polygon), "start_date": DATES["end_date"], "end_date": DATES["start_date"]})
    assert r.status_code == 422
    r = client.post(f"{BASE}/search", json={"aoi": {"monitored_area_id": "00000000-0000-0000-0000-000000000000"}})
    assert r.status_code == 404
    r = client.post(f"{BASE}/search", json={"aoi": {}})  # neither area nor geometry
    assert r.status_code == 422


def test_search_uses_monitored_area_geometry(client, db, wire, polygon):
    wire({"NISAR": FakeProvider(records=[make_record("A")])})
    area = client.post("/api/v1/areas", json={"name": "Test area", "geometry": polygon}).json()
    r = client.post(f"{BASE}/search", json={"aoi": {"monitored_area_id": area["id"]}})
    assert r.status_code == 200 and r.json()["aoi_name"] == "Test area"
    acq = client.get(f"{BASE}/acquisitions", params={"monitored_area_id": area["id"]}).json()
    assert acq["total"] == 1


def test_search_provider_failure_surfaces(client, wire, polygon):
    wire({"NISAR": FakeProvider(fail_search=RuntimeError("boom https://x/y?token=SECRET"))})
    r = client.post(f"{BASE}/search", json={"aoi": aoi(polygon)})
    assert r.status_code == 200 and r.json()["results"] == []
    assert "SECRET" not in r.json()["provider_errors"]["NISAR"]


def test_search_maturity_filter(client, wire, polygon):
    recs = [make_record("V"), make_record("P", maturity=Maturity.PROVISIONAL)]
    wire({"NISAR": FakeProvider(records=recs)})
    ids = lambda m: [x["granule_id"] for x in client.post(  # noqa: E731
        f"{BASE}/search", json={"aoi": aoi(polygon), "maturities": m, "dry_run": True}).json()["results"]]
    assert ids(["VALIDATED"]) == ["V"]
    assert sorted(ids(["VALIDATED", "PROVISIONAL"])) == ["P", "V"]


def test_search_disallowed_maturity_is_422(client, wire, polygon):
    wire({"NISAR": FakeProvider()}, allowed_maturities="VALIDATED")
    r = client.post(f"{BASE}/search", json={"aoi": aoi(polygon), "maturities": ["BETA"]})
    assert r.status_code == 422 and "ALLOWED_MATURITIES" in r.json()["error"]["message"]


# ---- acquisitions ----------------------------------------------------------------------
def test_acquisitions_filters_and_404(client, db, wire):
    wire({"NISAR": FakeProvider()})
    a, b = register(db, make_record("A", day=1), make_record("B", day=20, maturity=Maturity.PROVISIONAL))
    get = lambda **p: client.get(f"{BASE}/acquisitions", params=p).json()  # noqa: E731
    assert get()["total"] == 2
    assert [x["granule_id"] for x in get(maturity="PROVISIONAL")["items"]] == ["B"]
    assert get(product_type="GUNW")["total"] == 2 and get(product_type="DEM")["total"] == 0
    assert get(status="DISCOVERED")["total"] == 2 and get(status="VALIDATED")["total"] == 0
    assert [x["granule_id"] for x in get(start_date="2026-01-10T00:00:00Z")["items"]] == ["B"]
    assert [x["granule_id"] for x in get(end_date="2026-01-10T00:00:00Z")["items"]] == ["A"]
    assert get(limit=1, offset=1)["total"] == 2 and len(get(limit=1, offset=1)["items"]) == 1
    one = client.get(f"{BASE}/acquisitions/{a.id}").json()
    assert one["footprint"]["type"] == "Polygon" and one["local_file_path"] is None
    assert client.get(f"{BASE}/acquisitions/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get(f"{BASE}/acquisitions", params={"status": "bogus"}).status_code == 422


# ---- downloads -------------------------------------------------------------------------
def test_downloads_create_list_get_and_skipped(client, db, wire):
    prov = FakeProvider()
    wire({"NISAR": prov})
    [a] = register(db, make_record("A"))
    ghost = "00000000-0000-0000-0000-000000000000"
    r = client.post(f"{BASE}/downloads", json={"acquisition_ids": [str(a.id), ghost]})
    assert r.status_code == 202
    [job] = r.json()["jobs"]
    assert job["granule_id"] == "A" and job["product_type"] == "GUNW" and job["status"] == "COMPLETED"
    assert "not registered" in r.json()["skipped"][ghost]
    assert client.get(f"{BASE}/downloads/{job['id']}").json()["progress"] == 1.0
    assert client.get(f"{BASE}/downloads", params={"status": "COMPLETED"}).json()["total"] == 1
    assert client.get(f"{BASE}/downloads", params={"status": "FAILED"}).json()["items"] == []
    again = client.post(f"{BASE}/downloads", json={"acquisition_ids": [str(a.id)]}).json()
    assert again["jobs"] == [] and "already VALIDATED" in again["skipped"][str(a.id)]
    assert prov.downloads == 1
    assert client.get(f"{BASE}/downloads/{ghost}").status_code == 404
    assert client.post(f"{BASE}/downloads", json={"acquisition_ids": []}).status_code == 422


def test_retry_failed_job_409_and_404(client, db, wire):
    prov = FakeProvider(download_error=DownloadError("network down", retryable=False))
    wire({"NISAR": prov})
    [a, b] = register(db, make_record("A"), make_record("B", day=2))
    [job] = client.post(f"{BASE}/downloads", json={"acquisition_ids": [str(a.id)]}).json()["jobs"]
    assert job["status"] == "FAILED" and "network down" in job["error_message"]
    prov.download_error = None
    r = client.post(f"{BASE}/downloads/{job['id']}/retry")
    assert r.status_code == 202 and r.json()["status"] == "COMPLETED"
    r = client.post(f"{BASE}/downloads/{job['id']}/retry")  # now COMPLETED
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert client.post(f"{BASE}/downloads/00000000-0000-0000-0000-000000000000/retry").status_code == 404


def test_downloads_skip_oversized(client, db, wire):
    wire({"NISAR": FakeProvider()}, max_file_size_bytes=5)
    [a] = register(db, make_record("A", size=10))
    r = client.post(f"{BASE}/downloads", json={"acquisition_ids": [str(a.id)]}).json()
    assert r["jobs"] == [] and "max_file_size_bytes" in r["skipped"][str(a.id)]


# ---- environmental ---------------------------------------------------------------------
def env_providers(**kw):
    return {
        "NASADEM": FakeProvider(ProviderName.NASADEM, [make_record("DEM1", maturity=None, provider=ProviderName.NASADEM)]),
        "GPM": FakeProvider(ProviderName.GPM, [make_record("GPM1", maturity=None, provider=ProviderName.GPM)], **kw),
        "NISAR": FakeProvider(records=[make_record("NOT_ENV")]),
    }


def test_environmental_defaults_to_dry_run(client, db, wire, polygon):
    wire(env_providers())
    r = client.post(f"{BASE}/environmental/acquire", json={"aoi": aoi(polygon), **DATES})
    body = r.json()
    assert r.status_code == 200 and body["dry_run"] is True and body["jobs"] == []
    assert sorted(x["granule_id"] for x in body["results"]) == ["DEM1", "GPM1"]  # NISAR is not environmental
    assert n(db, DataAcquisition) == 0 and n(db, DownloadJob) == 0


def test_environmental_execute_isolates_provider_failure(client, db, wire, polygon):
    wire(env_providers(fail_search=RuntimeError("gpm down")))
    r = client.post(f"{BASE}/environmental/acquire", json={"aoi": aoi(polygon), **DATES, "dry_run": False}).json()
    assert [x["granule_id"] for x in r["results"]] == ["DEM1"] and "GPM" in r["provider_errors"]
    assert [j["granule_id"] for j in r["jobs"]] == ["DEM1"] and r["jobs"][0]["status"] == "COMPLETED"


def test_environmental_warnings(client, wire, polygon):
    wire(env_providers())  # SMAP not enabled; 40 days > max_granules=10
    r = client.post(f"{BASE}/environmental/acquire", json={
        "aoi": aoi(polygon), "start_date": "2026-01-01T00:00:00Z", "end_date": "2026-02-09T00:00:00Z",
        "include_smap": True}).json()
    text = " ".join(r["warnings"])
    assert "SMAP requested but disabled" in text and "one global file per day" in text
    bad = client.post(f"{BASE}/environmental/acquire", json={
        "aoi": aoi(polygon), "start_date": DATES["end_date"], "end_date": DATES["start_date"]})
    assert bad.status_code == 422


# ---- landslide events ------------------------------------------------------------------
def add_events(db):
    from geoalchemy2.shape import from_shape
    from shapely.geometry import Point

    for eid, lon, lat, country, year in (("E1", 10.0, 20.0, "Testland", 2010), ("E2", -70.0, -30.0, "Otherland", 2012)):
        db.add(LandslideEvent(
            external_event_id=eid, event_date=datetime(year, 1, 1, tzinfo=UTC), country=country,
            geometry=from_shape(Point(lon, lat), srid=4326), original_attributes={"synthetic": True},
            dataset_version="test-v1"))
    db.commit()


def test_landslide_events_filters_and_limitations(client, db):
    add_events(db)
    r = client.get(f"{BASE}/landslide-events").json()
    assert r["total"] == 2 and r["limitations"] == lc.LIMITATIONS and "2016-03-07" in r["limitations"]
    get = lambda **p: [e["external_event_id"] for e in client.get(f"{BASE}/landslide-events", params=p).json()["items"]]  # noqa: E731
    assert get(bbox="9,19,11,21") == ["E1"]
    assert get(country="otherland") == ["E2"]
    assert get(date_from="2011-01-01T00:00:00Z") == ["E2"]
    assert get(date_to="2011-01-01T00:00:00Z") == ["E1"]
    assert len(get(limit=1)) == 1
    assert client.get(f"{BASE}/landslide-events", params={"bbox": "1,2,3"}).status_code == 422
    assert client.get(f"{BASE}/landslide-events", params={"bbox": "5,0,1,9"}).status_code == 422


def test_landslide_import_from_file(client, db, wire, tmp_path):
    wire({})
    r = client.post(f"{BASE}/landslide-events/import", json={"file_path": str(write_csv(tmp_path))})
    assert r.status_code == 200
    assert (r.json()["inserted"], r.json()["skipped_invalid"]) == (3, 5)
    assert client.get(f"{BASE}/landslide-events").json()["total"] == 3
    assert client.post(f"{BASE}/landslide-events/import", json={"file_path": str(tmp_path / "nope.csv")}).status_code == 422
    assert client.post(f"{BASE}/landslide-events/import").status_code == 422  # explicit body required
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n")
    r = client.post(f"{BASE}/landslide-events/import", json={"file_path": str(bad)})
    assert r.status_code == 422 and "missing required column" in r.json()["error"]["message"]


def test_landslide_import_network_failure_is_502(client, wire, monkeypatch):
    wire({})

    def boom(self, *a, **k):
        raise RuntimeError("landslide catalog download failed after 3 attempts")

    monkeypatch.setattr(lc.LandslideCatalogProvider, "fetch", boom)
    r = client.post(f"{BASE}/landslide-events/import", json={"force": True})
    assert r.status_code == 502 and "download failed" in r.json()["error"]["message"]


# ---- status ----------------------------------------------------------------------------
def test_status_counts_and_never_leaks_credentials(client, db, wire, tmp_path):
    wire({"NISAR": FakeProvider()})
    a, _ = register(db, make_record("A"), make_record("B", day=2))
    client.post(f"{BASE}/downloads", json={"acquisition_ids": [str(a.id)]})
    add_events(db)
    r = client.get(f"{BASE}/status")
    assert r.status_code == 200
    s = r.json()
    assert s["acquisitions_registered"] == 2 and s["files_downloaded"] == 1 and s["files_validated"] == 1
    assert s["landslide_events"] == 2 and s["jobs_failed"] == 0 and s["product_distribution"] == {"GUNW": 2}
    assert s["earthdata_credentials_configured"] is True and s["data_root"] == str(tmp_path)
    assert s["storage_free_bytes"] > 0 and s["storage_used_bytes"] > 0
    assert {p["authentication"] for p in s["providers"]} <= {"not_required", "configured", "missing", "failed"}
    assert not any(secret in r.text for secret in SECRETS)
    assert not any(secret in json.dumps(client.get("/api/v1/system/info").json()) for secret in SECRETS)
