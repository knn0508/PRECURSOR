"""CLI tests: commands run over fake services. No network, no real NASA data."""
import json
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.cli import data_acquisition as cli
from app.core.config import Settings
from app.models import DataAcquisition
from app.services.data_acquisition.authentication import EarthdataAuthenticationService
from app.services.data_acquisition.orchestrator import AUTH_MESSAGE, AcquisitionOrchestrator
from app.services.data_acquisition.search_service import AcquisitionSearchService
from app.services.data_acquisition.types import AuthenticationError, DownloadError, ProviderError, ProviderName
from tests.data_acquisition.fakes import FakeProvider, FakeValidator, SyncExecutor, make_record

POLYGON = {"type": "Polygon", "coordinates": [[[44.0, 40.0], [44.1, 40.0], [44.1, 40.1], [44.0, 40.1], [44.0, 40.0]]]}


@pytest.fixture
def make(db, engine, tmp_path, monkeypatch):
    # no real ~/.netrc may make "missing" credentials look configured
    monkeypatch.setattr("app.services.data_acquisition.authentication._netrc_has_entry", lambda: False)

    def _make(providers=None, creds=True, **kw):
        providers = providers or {"NISAR": FakeProvider(records=[make_record("G1")])}
        s = Settings(**{
            "data_root": tmp_path, "allowed_maturities": "VALIDATED,PROVISIONAL,BETA",
            **({"earthdata_username": "u-fake", "earthdata_password": "p-fake"} if creds else {}), **kw})
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        orch = AcquisitionOrchestrator(factory, providers, FakeValidator(), s, executor=SyncExecutor())
        return cli.Services(
            s, EarthdataAuthenticationService(s, login_fn=lambda _: True),
            AcquisitionSearchService(providers, factory, s), orch, factory)

    return _make


@pytest.fixture
def aoi_file(tmp_path):
    p = tmp_path / "site.geojson"
    p.write_text(json.dumps(POLYGON))
    return p


def run(svc, *argv):
    lines: list[str] = []
    code = cli.run(cli.build_parser().parse_args(argv), svc, lines.append)
    return code, "\n".join(lines)


def count(db):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(DataAcquisition))


def test_discover_without_aoi_explains_and_exits_2(make):
    code, text = run(make(), "discover")
    assert code == 2 and "--aoi" in text and "aoi-configuration.md" in text


def test_discover_uses_single_file_in_aoi_dir(make, tmp_path):
    svc = make()
    (tmp_path / "aoi").mkdir()
    (tmp_path / "aoi" / "only.geojson").write_text(json.dumps(POLYGON))
    code, text = run(svc, "discover", "--dry-run")
    assert code == 0 and "G1" in text


def test_discover_dry_run_prints_and_writes_nothing(make, db, aoi_file):
    code, text = run(make(), "discover", "--aoi", str(aoi_file), "--dry-run")
    assert code == 0 and "G1" in text and "GUNW" in text and "Dry run" in text
    assert count(db) == 0


def test_discover_registers_metadata_only(make, db, aoi_file):
    code, text = run(make(), "discover", "--aoi", str(aoi_file), "--start-date", "2026-01-01")
    assert code == 0 and "metadata only" in text and count(db) == 1
    assert db.scalar(select(DataAcquisition.status)) == "DISCOVERED"


def test_exit_codes(make, aoi_file):
    assert run(make(), "discover", "--aoi", "missing.geojson")[0] == 2
    assert run(make(), "discover", "--aoi", str(aoi_file), "--start-date", "yesterday")[0] == 2
    failing = {"NISAR": FakeProvider(fail_search=RuntimeError("down"))}
    code, text = run(make(failing), "discover", "--aoi", str(aoi_file), "--dry-run")
    assert code == 3 and "NISAR" in text
    with pytest.raises(SystemExit) as e:  # argparse usage error
        cli.build_parser().parse_args(["discover", "--maturities", "NOPE"])
    assert e.value.code == 2

    def raiser(exc):
        def f(args, svc, out):
            raise exc
        return f

    args = cli.build_parser().parse_args(["status"])
    for exc, want in ((AuthenticationError("x"), 4), (ProviderError("x"), 3), (ValueError("x"), 2), (DownloadError("x"), 3)):
        args.func = raiser(exc)
        assert cli.run(args, make(), lambda _: None) == want


def test_download_requires_registration_and_credentials(make, db, aoi_file):
    svc = make()
    assert run(svc, "download", "--granule-id", "G1")[0] == 2  # not registered
    run(svc, "discover", "--aoi", str(aoi_file))
    code, text = run(make(creds=False), "download", "--granule-id", "G1")
    assert code == 4 and "EARTHDATA_USERNAME" in text
    assert db.scalar(select(DataAcquisition.status)) == "DISCOVERED"  # nothing queued without credentials


def test_download_runs_job_then_skips_repeat(make, db, aoi_file):
    prov = FakeProvider(records=[make_record("G1")])
    svc = make({"NISAR": prov})
    run(svc, "discover", "--aoi", str(aoi_file))
    code, text = run(svc, "download", "--granule-id", "G1")
    assert code == 0 and "G1: COMPLETED" in text and prov.downloads == 1
    code, text = run(svc, "download", "--granule-id", "G1")
    assert code == 0 and "already VALIDATED" in text and prov.downloads == 1


def test_download_failure_maps_exit_code_and_retry(make, db, aoi_file):
    prov = FakeProvider(records=[make_record("G1")], download_error=DownloadError("net", retryable=False))
    svc = make({"NISAR": prov})
    run(svc, "discover", "--aoi", str(aoi_file))
    code, text = run(svc, "download", "--granule-id", "G1")
    assert code == 3 and "FAILED" in text
    db.expire_all()
    job_id = str(db.scalar(select(DataAcquisition).where(DataAcquisition.granule_id == "G1")).jobs[0].id)
    prov.download_error = None
    assert run(svc, "retry", job_id)[0] == 0
    assert run(svc, "retry", job_id)[0] == 2  # only FAILED jobs can be retried
    assert run(svc, "retry", str(uuid.uuid4()))[0] == 2
    assert run(svc, "retry", "not-a-uuid")[0] == 2


def test_auth_failed_job_exits_4(make, db, aoi_file):
    prov = FakeProvider(records=[make_record("G1")], download_error=AuthenticationError("x"))
    svc = make({"NISAR": prov})
    run(svc, "discover", "--aoi", str(aoi_file))
    code, text = run(svc, "download", "--granule-id", "G1")
    assert code == 4 and AUTH_MESSAGE in text


def test_acquire_environmental_dry_run_then_execute(make, db, aoi_file):
    provs = {
        "NASADEM": FakeProvider(ProviderName.NASADEM, [make_record("DEM1", maturity=None, provider=ProviderName.NASADEM)]),
        "GPM": FakeProvider(ProviderName.GPM, [make_record("GPM1", maturity=None, provider=ProviderName.GPM)]),
    }
    svc = make(provs)
    common = ("acquire-environmental", "--aoi", str(aoi_file), "--start-date", "2026-01-01", "--end-date", "2026-01-05")
    code, text = run(svc, *common)
    assert code == 0 and "DEM1" in text and "GPM1" in text and "Dry run" in text and count(db) == 0
    code, text = run(svc, *common, "--execute")
    assert code == 0 and "DEM1: COMPLETED" in text and count(db) == 2
    assert run(svc, *common[:-1], "2025-01-01")[0] == 2  # end before start
    assert run(make(provs, creds=False), *common, "--execute")[0] == 4


def test_collections_status_history_work_without_aoi_or_credentials(make, db):
    svc = make(creds=False)
    code, text = run(svc, "collections", "--discover")
    assert code == 0 and "FAKE_COLL" in text
    code, text = run(svc, "status")
    assert code == 0 and "configured: False" in text and "u-fake" not in text
    assert run(svc, "history")[0] == 0


def test_import_landslides_from_file(make, tmp_path):
    from tests.data_acquisition.test_landslide_catalog import write_csv

    svc = make()
    code, text = run(svc, "import-landslides", "--file", str(write_csv(tmp_path)))
    assert code == 0 and "inserted 3" in text and "2017-09-28" in text
    assert run(svc, "import-landslides", "--file", str(tmp_path / "nope.csv"))[0] == 2


def test_revalidate(make, db, aoi_file):
    svc = make()
    run(svc, "discover", "--aoi", str(aoi_file))
    run(svc, "download", "--granule-id", "G1")
    db.expire_all()
    acq_id = str(db.scalar(select(DataAcquisition.id)))
    code, text = run(svc, "revalidate", acq_id)
    assert code == 0 and "VALIDATED" in text and "not a scientific validation" in text
    assert run(svc, "revalidate", str(uuid.uuid4()))[0] == 2
