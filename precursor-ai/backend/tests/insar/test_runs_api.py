"""Phase 2 -> Phase 3 integration: DB persistence, run lifecycle, API behaviour, file-access safety.
All inputs are SYNTHETIC fixtures; passing here is NOT evidence of real satellite processing."""
import shutil
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.api.v1 import insar as insar_api
from app.core.config import Settings, get_settings
from app.main import app
from app.models import DataAcquisition, DataCollection, DeformationProduct, InSARProcessingRun
from app.services.insar import storage, synthetic
from app.services.insar.runs import InSARRunService
from app.services.insar.types import RunStatus
from tests.data_acquisition.fakes import SyncExecutor

BASE = "/api/v1/insar"


@pytest.fixture
def env(client, db, engine, tmp_path):
    settings = Settings(data_root=tmp_path, insar_min_free_disk_bytes=0)
    storage.ensure_layout(tmp_path)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    svc = InSARRunService(factory, settings, executor=SyncExecutor())
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[insar_api.get_insar_service] = lambda: svc
    return type("Env", (), {"svc": svc, "root": tmp_path, "settings": settings, "client": client, "db": db})


def put_sample(env, name="s.h5", maker=synthetic.make_gunw, **kw):
    return maker(storage.samples_dir(env.root) / name, **kw)


def register_acq(env, status="VALIDATED", product="GUNW", with_file=True, maker=synthetic.make_gunw, **kw):
    db = env.db
    col = DataCollection(provider="NISAR", collection_short_name=f"C_{uuid.uuid4().hex[:6]}", dataset_name="x",
                         product_type=product, version="1")
    db.add(col)
    db.flush()
    rel = f"raw/nisar/{product.lower()}/20251001__G1.h5"
    if with_file:
        (env.root / rel).parent.mkdir(parents=True, exist_ok=True)
        maker(env.root / rel, **kw)
    a = DataAcquisition(
        collection_id=col.id, provider="NISAR", granule_id=f"G-{uuid.uuid4().hex[:6]}", product_type=product,
        status=status, local_file_path=rel if with_file else None, maturity="VALIDATED",
        acquisition_start=datetime(2025, 10, 1, tzinfo=UTC), file_size_bytes=1, validation_report={"passed": True})
    db.add(a)
    db.commit()
    return a


def post_run(env, **body):
    return env.client.post(f"{BASE}/processing-runs", json=body)


# --- product listing & input selection -------------------------------------------------------------
def test_products_empty_without_files_and_says_nothing_is_downloaded(env):
    r = env.client.get(f"{BASE}/products").json()
    assert r["items"] == [] and "nothing is downloaded" in r["note"].lower()


def test_discovered_but_not_downloaded_acquisition_is_not_processable(env):
    a = register_acq(env, status="DISCOVERED", with_file=False)
    assert env.client.get(f"{BASE}/products").json()["items"] == []
    r = post_run(env, acquisition_id=str(a.id))
    assert r.status_code == 422 and "not processable" in r.json()["error"]["message"]
    assert env.db.scalar(select(func.count()).select_from(InSARProcessingRun)) == 0


def test_listing_shows_downloaded_acquisitions_and_samples_only_other_types_excluded(env):
    a = register_acq(env)
    register_acq(env, product="GOFF", with_file=False)
    put_sample(env, "demo.h5")
    items = {i["id"]: i for i in env.client.get(f"{BASE}/products").json()["items"]}
    assert str(a.id) in items and items[str(a.id)]["source"] == "ACQUISITION"
    assert items["sample:demo.h5"]["source"] == "SAMPLE" and items["sample:demo.h5"]["product_type"] == "GUNW"
    assert len(items) == 2


def test_inspect_acquisition_and_sample(env):
    a = register_acq(env)
    put_sample(env)
    r = env.client.get(f"{BASE}/products/{a.id}").json()
    assert r["product_kind"] == "GUNW" and r["displacement_supported"] is True
    assert r["data_origin"] == "SYNTHETIC_FIXTURE"  # the marker wins over the "registered acquisition" hint
    r = env.client.post(f"{BASE}/inspect", json={"sample_file": "s.h5"}).json()
    assert r["product_kind"] == "GUNW"


@pytest.mark.parametrize("body", [{}, {"sample_file": "a.h5", "acquisition_id": str(uuid.uuid4())}])
def test_input_requires_exactly_one_reference(env, body):
    assert env.client.post(f"{BASE}/inspect", json=body).status_code == 422
    assert post_run(env, **body).status_code == 422


@pytest.mark.parametrize("name", ["../secret.h5", "a/b.h5", "..", ".hidden", "C:\\x.h5"])
def test_sample_names_cannot_traverse(env, name):
    assert env.client.post(f"{BASE}/inspect", json={"sample_file": name}).status_code == 422
    assert post_run(env, sample_file=name).status_code == 422


def test_unknown_ids_are_404(env):
    assert env.client.get(f"{BASE}/processing-runs/{uuid.uuid4()}").status_code == 404
    assert env.client.get(f"{BASE}/deformation-products/{uuid.uuid4()}").status_code == 404
    assert post_run(env, acquisition_id=str(uuid.uuid4())).status_code == 404
    assert post_run(env, sample_file="nope.h5").status_code == 404
    assert env.client.get(f"{BASE}/products/not-a-uuid").status_code == 422


def test_acquisition_with_missing_file_is_rejected(env):
    a = register_acq(env)
    (env.root / a.local_file_path).unlink()
    assert post_run(env, acquisition_id=str(a.id)).status_code == 422


def test_acquisition_path_outside_raw_is_rejected(env):
    a = register_acq(env)
    a.local_file_path = "samples/insar/x.h5"
    env.db.commit()
    assert post_run(env, acquisition_id=str(a.id)).status_code == 422


# --- full run lifecycle ------------------------------------------------------------------------------
def test_gunw_run_completes_persists_and_serves_rasters(env):
    a = register_acq(env)
    r = post_run(env, acquisition_id=str(a.id), config={"block_rows": 16})
    assert r.status_code == 202 and r.json()["created"] is True
    run_id = r.json()["run"]["id"]

    run = env.client.get(f"{BASE}/processing-runs/{run_id}").json()
    assert run["status"] == "COMPLETED" and run["progress"] == 1.0
    assert run["acquisition_id"] == str(a.id) and run["data_origin"] == "SYNTHETIC_FIXTURE"
    stages = {s["name"]: s["status"] for s in run["stages"]}
    assert stages["INSPECTING"] == "DONE" and stages["PREPROCESSING"] == "SKIPPED"
    assert stages["DISPLACEMENT_CALCULATION"] == "DONE" and stages["QUALITY_CHECK"] == "DONE"
    kinds = {p["product_type"] for p in run["products"]}
    assert kinds == {"LOS_DISPLACEMENT", "COHERENCE", "LOS_VELOCITY"}
    disp = next(p for p in run["products"] if p["product_type"] == "LOS_DISPLACEMENT")
    assert disp["units"] == "mm" and disp["crs"] == "EPSG:32618" and disp["scientifically_validated"] is False
    assert "SYNTHETIC" in disp["label"] and disp["footprint"]["type"] == "Polygon"
    assert disp["reference_time"] and disp["secondary_time"] and disp["statistics"]["valid_pixels"] > 0
    assert not disp["file_size_bytes"] is None

    st = env.client.get(f"{BASE}/processing-runs/{run_id}/status").json()
    assert st["terminal"] is True and st["status"] == "COMPLETED"
    q = env.client.get(f"{BASE}/processing-runs/{run_id}/quality").json()
    assert q["real_satellite_data"] is False and q["real_data_validation"] == "NOT_PERFORMED"
    assert q["file_integrity_validation"]["note"].startswith("file integrity only")

    raster = env.client.get(f"{BASE}/deformation-products/{disp['id']}/raster")
    assert raster.status_code == 200 and raster.headers["content-type"] == "image/tiff"
    assert raster.headers["x-data-origin"] == "SYNTHETIC_FIXTURE" and raster.content[:4] in (b"II*\x00", b"MM\x00*")
    png = env.client.get(f"{BASE}/deformation-products/{disp['id']}/preview", params={"vmax": 50})
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n" and png.headers["x-scale"] == "vmax=50.0"

    lst = env.client.get(f"{BASE}/deformation-products", params={"product_type": "COHERENCE"}).json()
    assert lst["total"] == 1 and lst["items"][0]["units"] == "dimensionless"
    assert env.client.get(f"{BASE}/deformation-products/{disp['id']}").json()["id"] == disp["id"]
    runs = env.client.get(f"{BASE}/processing-runs", params={"status": "COMPLETED"}).json()
    assert runs["total"] == 1 and runs["items"][0]["id"] == run_id

    # files on disk: quality + inspection + metadata json, no intermediates left behind
    assert (env.root / "processed/insar/quality_reports" / run_id / "quality_report.json").is_file()
    assert (env.root / "processed/insar/inspections" / run_id / "inspection.json").is_file()
    assert not list((env.root / "processed/insar/intermediate" / run_id).glob("*"))
    # the Phase 2 row and its raw file are untouched
    env.db.refresh(a)
    assert a.status == "VALIDATED" and (env.root / a.local_file_path).is_file()


def test_duplicate_run_returns_existing_unless_forced(env):
    put_sample(env)
    first = post_run(env, sample_file="s.h5").json()
    again = post_run(env, sample_file="s.h5")
    assert again.status_code == 200 and again.json()["created"] is False
    assert again.json()["run"]["id"] == first["run"]["id"]
    other_cfg = post_run(env, sample_file="s.h5", config={"coherence_threshold": 0.5}).json()
    assert other_cfg["created"] is True and other_cfg["run"]["id"] != first["run"]["id"]
    forced = post_run(env, sample_file="s.h5", force=True).json()
    assert forced["created"] is True
    assert env.db.scalar(select(func.count()).select_from(InSARProcessingRun)) == 3


def test_threshold_run_masks_in_persisted_stats(env):
    put_sample(env)
    rid = post_run(env, sample_file="s.h5", config={"coherence_threshold": 0.5}).json()["run"]["id"]
    q = env.client.get(f"{BASE}/processing-runs/{rid}/quality").json()
    assert q["configuration"]["coherence_threshold"] == 0.5
    assert q["statistics"]["masked_by_coherence_threshold"] == 6 * 40


def test_unsupported_displacement_fails_loudly_with_report(env):
    put_sample(env, with_frequency=False)
    rid = post_run(env, sample_file="s.h5").json()["run"]["id"]
    run = env.client.get(f"{BASE}/processing-runs/{rid}").json()
    assert run["status"] == "FAILED" and "not supported" in run["error_message"] and run["products"] == []
    q = env.client.get(f"{BASE}/processing-runs/{rid}/quality").json()
    assert q["status"] == "FAILED" and q["errors"] and q["real_data_validation"] == "NOT_PERFORMED"
    assert env.db.scalar(select(func.count()).select_from(DeformationProduct)) == 0


@pytest.mark.parametrize("maker,kind", [(synthetic.make_gslc, "GSLC"), (synthetic.make_gcov, "GCOV")])
def test_gslc_gcov_runs_are_inspection_only(env, maker, kind):
    put_sample(env, "x.h5", maker)
    rid = post_run(env, sample_file="x.h5").json()["run"]["id"]
    run = env.client.get(f"{BASE}/processing-runs/{rid}").json()
    assert run["status"] == "COMPLETED" and run["product_kind"] == kind and run["products"] == []
    stages = {s["name"]: s["status"] for s in run["stages"]}
    assert stages["DISPLACEMENT_CALCULATION"] == "SKIPPED"
    q = env.client.get(f"{BASE}/processing-runs/{rid}/quality").json()
    assert any("inspection-only" in w for w in q["warnings"])


def test_sentinel1_run_is_blocked_missing_input(env):
    name = "S1A_IW_SLC__1SDV_20240101T120000_20240101T120027_051234_063ABC_1234.zip"
    (storage.samples_dir(env.root) / name).write_bytes(b"PK\x05\x06" + b"\0" * 18)
    rid = post_run(env, sample_file=name).json()["run"]["id"]
    run = env.client.get(f"{BASE}/processing-runs/{rid}").json()
    assert run["status"] == "BLOCKED_MISSING_INPUT" and "not available" in run["error_message"]
    assert run["products"] == []


def test_unrecognised_file_fails(env):
    (storage.samples_dir(env.root) / "junk.bin").write_bytes(b"junk")
    rid = post_run(env, sample_file="junk.bin").json()["run"]["id"]
    assert env.client.get(f"{BASE}/processing-runs/{rid}").json()["status"] == "FAILED"


def test_input_deleted_between_create_and_execute_is_blocked(env):
    f = put_sample(env)
    run, _ = env.svc.create_run(env.db, None, "s.h5", __import__("app.services.insar.types", fromlist=["x"]).ProcessingConfig())
    f.unlink()
    env.svc.execute(run.id)
    env.db.refresh(run)
    assert run.status == RunStatus.BLOCKED_MISSING_INPUT.value


def test_cancel_queued_and_finished(env):
    from app.services.insar.types import ProcessingConfig

    put_sample(env)
    run, _ = env.svc.create_run(env.db, None, "s.h5", ProcessingConfig())  # QUEUED, not executed yet
    r = env.client.post(f"{BASE}/processing-runs/{run.id}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    env.svc.execute(run.id)  # a cancelled run is never executed
    env.db.refresh(run)
    assert run.status == "CANCELLED" and env.db.scalar(select(func.count()).select_from(DeformationProduct)) == 0
    assert env.client.post(f"{BASE}/processing-runs/{run.id}/cancel").status_code == 409


def test_cancel_during_processing_stops_the_run(env):
    from app.services.insar.types import ProcessingConfig

    put_sample(env)
    run, _ = env.svc.create_run(env.db, None, "s.h5", ProcessingConfig())
    run.cancel_requested = True  # requested before the worker starts checking blocks
    env.db.commit()
    env.svc.execute(run.id)
    env.db.refresh(run)
    assert run.status == "CANCELLED" and "cancelled" in run.error_message


def test_stale_runs_are_failed_on_recovery(env):
    from app.services.insar.types import ProcessingConfig

    put_sample(env)
    run, _ = env.svc.create_run(env.db, None, "s.h5", ProcessingConfig())
    assert env.svc.recover_stale_runs() == 1
    env.db.refresh(run)
    assert run.status == "FAILED" and "restart" in run.error_message
    assert env.svc.recover_stale_runs() == 0


# --- controlled file access ----------------------------------------------------------------------------
def test_raster_endpoint_refuses_paths_outside_processed_insar(env):
    put_sample(env)
    rid = post_run(env, sample_file="s.h5").json()["run"]["id"]
    p = env.db.scalars(select(DeformationProduct).where(DeformationProduct.run_id == uuid.UUID(rid))).first()
    p.file_path = "raw/nisar/gunw/secret.h5"
    env.db.commit()
    for suffix in ("raster", "preview"):
        r = env.client.get(f"{BASE}/deformation-products/{p.id}/{suffix}")
        assert r.status_code == 404 and "secret" not in r.text
    p.file_path = "../../outside.tif"
    env.db.commit()
    assert env.client.get(f"{BASE}/deformation-products/{p.id}/raster").status_code == 404


def test_missing_raster_file_is_404_not_500(env):
    put_sample(env)
    rid = post_run(env, sample_file="s.h5").json()["run"]["id"]
    p = env.db.scalars(select(DeformationProduct).where(DeformationProduct.run_id == uuid.UUID(rid))).first()
    shutil.rmtree(env.root / "processed/insar/displacement")
    shutil.rmtree(env.root / "processed/insar/coherence")
    shutil.rmtree(env.root / "processed/insar/velocity")
    assert env.client.get(f"{BASE}/deformation-products/{p.id}/raster").status_code == 404


def test_responses_never_expose_absolute_paths_or_credentials(env):
    put_sample(env)
    rid = post_run(env, sample_file="s.h5").json()["run"]["id"]
    blob = " ".join(env.client.get(f"{BASE}/{u}").text for u in (
        f"processing-runs/{rid}", f"processing-runs/{rid}/quality", "deformation-products", "products"))
    assert str(env.root) not in blob and str(env.root).replace("\\", "/") not in blob
    assert "EARTHDATA" not in blob.upper() and "password" not in blob.lower()


def test_no_network_or_download_code_is_reachable_from_insar_package():
    import pathlib

    src = "\n".join(p.read_text(encoding="utf-8") for p in pathlib.Path("app/services/insar").rglob("*.py"))
    for banned in ("earthaccess", "asf_search", "requests", "urllib", "httpx", "EarthdataAuthenticationService"):
        assert banned not in src, banned


def test_system_info_reports_insar_available_without_overclaiming(plain_client):
    mods = {m["name"]: m for m in plain_client.get("/api/v1/system/info").json()["modules"]}
    assert mods["insar"]["status"] == "available" and "not performed" in mods["insar"]["description"]
    assert mods["risk_assessment"]["status"] == "planned"
