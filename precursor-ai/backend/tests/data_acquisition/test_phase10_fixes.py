"""Phase 10 regression tests for Phase 2 defects #1 (file_path import reads any server path), #2 (credential pre-check),
#7 (retry resets attempts) and #8 (test isolation from real Earthdata credentials). No network."""
import os

from sqlalchemy import func, select

from app.api.v1.data import deps
from app.core.config import Settings
from app.main import app
from app.models import DataAcquisition, DownloadJob
from app.services.data_acquisition import authentication
from app.services.data_acquisition.authentication import EarthdataAuthenticationService
from app.services.data_acquisition.types import DownloadError
from tests.data_acquisition.fakes import FakeProvider, make_record
from tests.data_acquisition.test_api_data import BASE, register, wire  # noqa: F401  (wire is a fixture)
from tests.data_acquisition.test_landslide_catalog import write_csv


# ---- #1 path confinement ----------------------------------------------------------------
def test_import_file_path_outside_data_root_is_refused(client, db, wire, tmp_path):  # noqa: F811
    root = tmp_path / "data"
    root.mkdir()
    wire({}, data_root=root)
    outside = tmp_path / "outside"
    outside.mkdir()
    csv = write_csv(outside)  # a perfectly valid catalog, but not under the data root
    r = client.post(f"{BASE}/landslide-events/import", json={"file_path": str(csv)})
    assert r.status_code == 422 and "inside the configured data root" in r.json()["error"]["message"]
    assert client.get(f"{BASE}/landslide-events").json()["total"] == 0  # nothing was read or imported


def test_import_file_path_traversal_and_system_paths_are_refused(client, db, wire, tmp_path):  # noqa: F811
    root = tmp_path / "data"
    (root / "sub").mkdir(parents=True)
    wire({}, data_root=root)
    csv = write_csv(tmp_path)  # sits in tmp_path, the parent of the data root
    for p in (str(root / "sub" / ".." / ".." / csv.name), os.path.abspath(os.sep), str(csv), "../../../etc/passwd"):
        r = client.post(f"{BASE}/landslide-events/import", json={"file_path": p})
        assert r.status_code == 422, p


def test_import_file_path_inside_data_root_still_works(client, db, wire, tmp_path):  # noqa: F811
    root = tmp_path / "data"
    (root / "raw").mkdir(parents=True)
    wire({}, data_root=root)
    csv = write_csv(root / "raw")
    r = client.post(f"{BASE}/landslide-events/import", json={"file_path": str(csv)})
    assert r.status_code == 200 and r.json()["inserted"] == 3


# ---- #2 credential pre-check ------------------------------------------------------------
def test_downloads_refused_up_front_without_credentials(client, db, wire, monkeypatch):  # noqa: F811
    monkeypatch.setattr(authentication, "_netrc_has_entry", lambda: False)
    wire({"NISAR": FakeProvider()})
    nocred = Settings(_env_file=None, earthdata_username=None, earthdata_password=None)
    app.dependency_overrides[deps.get_auth] = lambda: EarthdataAuthenticationService(nocred, login_fn=lambda s: True)
    [a] = register(db, make_record("A"))
    r = client.post(f"{BASE}/downloads", json={"acquisition_ids": [str(a.id)]})
    assert r.status_code == 412 and r.json()["error"]["code"] == "credentials_missing"
    assert "EARTHDATA_USERNAME" in r.json()["error"]["message"]
    assert db.scalar(select(func.count()).select_from(DownloadJob)) == 0  # nothing queued
    db.expire_all()
    assert db.get(DataAcquisition, a.id).status == "DISCOVERED"  # and the acquisition was not moved to QUEUED


# ---- #7 retry resets attempts -----------------------------------------------------------
def test_retry_starts_a_fresh_attempt_series(client, db, wire):  # noqa: F811
    prov = FakeProvider(download_error=DownloadError("network down", retryable=False))
    wire({"NISAR": prov})
    [a] = register(db, make_record("A"))
    [job] = client.post(f"{BASE}/downloads", json={"acquisition_ids": [str(a.id)]}).json()["jobs"]
    assert job["status"] == "FAILED" and job["attempts"] == 1
    r = client.post(f"{BASE}/downloads/{job['id']}/retry")  # still failing: attempts must be 1 again, not 2
    assert r.status_code == 202 and r.json()["status"] == "FAILED" and r.json()["attempts"] == 1


# ---- #8 isolation from real credentials -------------------------------------------------
def test_environment_credentials_do_not_leak_into_tests():
    assert "EARTHDATA_USERNAME" not in os.environ and "EARTHDATA_PASSWORD" not in os.environ
