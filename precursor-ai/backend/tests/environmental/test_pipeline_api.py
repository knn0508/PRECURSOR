"""Phase 4 integration: Phase 2 records + files -> pipeline -> DB -> API.

EVERYTHING here is SYNTHETIC (rasters, IMERG-like files, catalog rows, earthquakes, deformation rows). Rows labelled as
"test double" only exercise provenance/eligibility logic. Passing proves wiring and honesty rules, NOT real-data validity.
"""
import uuid
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest
from geoalchemy2.shape import from_shape
from shapely.geometry import Point, box
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.api.v1 import environmental as env_api
from app.core.config import Settings, get_settings
from app.main import app
from app.models import (
    DataAcquisition, DataCollection, DeformationProduct, EarthquakeEvent, EnvironmentalFeature, EnvironmentalLayer,
    EnvironmentalProcessingRun, InSARProcessingRun, LandslideEvent, MonitoredArea,
)
from app.services.environmental import storage, synthetic_raster as sr
from app.services.environmental.pipeline.runs import EnvironmentalRunService
from app.services.environmental.providers import synthetic as ps
from app.services.environmental.providers.usgs_earthquake import FetchResult
from app.services.environmental.rainfall.synthetic import write_synthetic_imerg
from tests.data_acquisition.fakes import SyncExecutor

BASE = "/api/v1/environmental"
AREA = box(116.001, 5.191, 116.010, 5.199)  # inside the synthetic DEM tile and the synthetic rainfall grid
RAIN_LAT = 5.0 + 0.1 * np.arange(10)
RAIN_LON = 115.9 + 0.1 * np.arange(12)  # non-square: the reader refuses ambiguous axis order


class FakeUSGS:
    """No network: returns canned events (and records the calls)."""

    def __init__(self, events=None, error=None):
        self.events, self.error, self.calls = events or [], error, []

    def fetch(self, bbox, start, end, min_magnitude=None, session=None):
        self.calls.append((bbox, start, end, min_magnitude))
        if self.error:
            raise self.error
        return FetchResult(events=list(self.events), warnings=["synthetic fake"], truncated=False, pages=1)


def quake(eid, lon=116.005, lat=5.195, mag=4.5, day=3):
    return {"id": eid, "time": datetime(2024, 1, day, tzinfo=UTC), "magnitude": mag, "mag_type": "mww", "depth_km": 10.0,
            "place": "synthetic place", "url": "https://example.invalid/" + eid, "status": "reviewed", "lon": lon, "lat": lat, "properties": {}}


@pytest.fixture
def env(client, db, engine, tmp_path):
    settings = Settings(data_root=tmp_path)
    storage.ensure_layout(tmp_path)
    svc = EnvironmentalRunService(sessionmaker(bind=engine, expire_on_commit=False), settings, executor=SyncExecutor())
    usgs = FakeUSGS([quake("us1"), quake("us2", day=5)])
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[env_api.get_env_service] = lambda: svc
    app.dependency_overrides[env_api.get_usgs] = lambda: usgs
    return type("Env", (), {"svc": svc, "root": tmp_path, "client": client, "db": db, "usgs": usgs})


def make_area(env, poly=AREA, name="synthetic-test-area"):
    a = MonitoredArea(name=name, geometry=from_shape(poly, srid=4326))
    env.db.add(a)
    env.db.commit()
    return a


def _col(db, provider):
    c = DataCollection(provider=provider, collection_short_name=f"{provider}_{uuid.uuid4().hex[:5]}", dataset_name=provider,
                       product_type="X", version="1")
    db.add(c)
    db.flush()
    return c


def seed_dem(env, *, corrupt=False):
    rel = "raw/nasadem/20000211__NASADEM_HGT_synthetic.tif"
    f = env.root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    if corrupt:
        f.write_bytes(b"not a raster")
    else:
        sr.make_plane_geographic(f, lat0=5.2)
    a = DataAcquisition(collection_id=_col(env.db, "NASADEM").id, provider="NASADEM", granule_id=f"DEM-{uuid.uuid4().hex[:5]}",
                        product_type="DEM", status="VALIDATED", local_file_path=rel, spatial_footprint=from_shape(box(116.0, 5.188, 116.0115, 5.2), srid=4326))
    env.db.add(a)
    env.db.commit()
    return a


def seed_gpm(env, days=10, missing=(4,)):
    col = _col(env.db, "GPM")
    out = []
    for i in range(days):
        if i in missing:
            continue
        day = date(2024, 1, 1) + timedelta(days=i)
        rel = f"raw/gpm/imerg/{day:%Y%m%d}__synthetic.HDF5"
        (env.root / rel).parent.mkdir(parents=True, exist_ok=True)
        write_synthetic_imerg(env.root / rel, day, lat=RAIN_LAT, lon=RAIN_LON)
        a = DataAcquisition(collection_id=col.id, provider="GPM", granule_id=f"GPM-{day:%Y%m%d}", product_type="IMERG", status="VALIDATED",
                            local_file_path=rel, acquisition_start=datetime.combine(day, datetime.min.time(), UTC))
        env.db.add(a)
        out.append(a)
    env.db.commit()
    return out


def seed_external(env):
    sd = storage.external_dir(env.root, "soilgrids")
    sd.mkdir(parents=True, exist_ok=True)
    ps.write_synthetic_soil(sd, "clay", 0, 5, "mean", np.full((10, 10), 300, dtype="int16"), west=115.9, north=5.3, pixel=0.1)
    ld = storage.external_dir(env.root, "land_cover")
    ld.mkdir(parents=True, exist_ok=True)
    ps.write_synthetic_land_cover(ld / "ESA_WorldCover_synthetic.tif", np.full((10, 10), 10, dtype="uint8"), west=115.9, north=5.3, pixel=0.1)


def seed_events(env):
    env.db.add(LandslideEvent(external_event_id="SYN-1", event_date=datetime(2012, 5, 1, tzinfo=UTC), geometry=from_shape(Point(116.004, 5.195), srid=4326),
                              dataset_version="synthetic-test", original_attributes={}))
    env.db.add(LandslideEvent(external_event_id="SYN-FAR", event_date=datetime(2010, 5, 1, tzinfo=UTC), geometry=from_shape(Point(100.0, 1.0), srid=4326),
                              dataset_version="synthetic-test", original_attributes={}))
    env.db.commit()


def seed_insar(env):
    """Test doubles: one SYNTHETIC product and one labelled REAL_SATELLITE row (no file) to exercise eligibility."""
    run = InSARProcessingRun(input_kind="SAMPLE", input_ref="x", config_hash="h", status="COMPLETED")
    env.db.add(run)
    env.db.flush()
    for origin, ptype in (("SYNTHETIC_FIXTURE", "LOS_DISPLACEMENT"), ("REAL_SATELLITE", "LOS_VELOCITY")):
        env.db.add(DeformationProduct(run_id=run.id, product_type=ptype, file_path="x.tif", units="mm" if ptype == "LOS_DISPLACEMENT" else "mm/year",
                                      width=2, height=2, data_origin=origin, scientifically_validated=False,
                                      statistics={"mean": -3.0, "min": -9.0, "max": 0.0, "valid_pixels": 4},
                                      footprint=from_shape(box(116.0, 5.18, 116.02, 5.21), srid=4326)))
    env.db.commit()


def process(env, area, **cfg):
    r = env.client.post(f"{BASE}/areas/{area.id}/process", json=cfg or None)
    assert r.status_code == 202, r.text
    return r.json()["run"]["id"]


def stages(env, run_id):
    run = env.client.get(f"{BASE}/processing-runs/{run_id}").json()
    return run, {s["name"]: s["status"] for s in run["stages"]}


# --- nothing available -----------------------------------------------------------------------------
def test_empty_area_runs_partial_and_nothing_is_filled(env):
    a = make_area(env)
    rid = process(env, a)
    run, st = stages(env, rid)
    assert run["status"] == "PARTIAL" and run["error_message"] is None
    assert st["DEM"] == st["RAINFALL"] == st["SOIL"] == st["LAND_COVER"] == st["INSAR"] == "NOT_AVAILABLE"
    assert st["HISTORICAL_LANDSLIDES"] == st["SEISMIC"] == "NOT_AVAILABLE" and st["FEATURES"] == st["QUALITY"] == "DONE"
    assert any("no source data available" in w for w in run["warnings"])
    cov = env.client.get(f"{BASE}/areas/{a.id}/coverage").json()
    assert cov["items"] and all(not i["available"] for i in cov["items"]) and all(i["reason"] for i in cov["items"])
    assert {i["status"] for i in cov["items"]} == {"NOT_AVAILABLE"}
    na = env.client.get(f"{BASE}/areas/{a.id}/layers").json()["items"]
    assert na and all("not a zero value" in l["label"] and "unverified" not in l["label"].lower() for l in na)
    for ep in ("terrain", "soil", "land-cover"):
        f = env.client.get(f"{BASE}/areas/{a.id}/{ep}").json()
        assert f["status"] == "NOT_AVAILABLE" and f["values"] == {} and "not a zero" in f["label"].lower() or f["values"] == {}
    rain = env.client.get(f"{BASE}/areas/{a.id}/rainfall").json()
    assert rain["daily"] == [] and rain["observed_days"] == 0
    for ep in ("historical-landslides", "seismic"):
        ev = env.client.get(f"{BASE}/areas/{a.id}/{ep}").json()
        assert ev["status"] == "NOT_AVAILABLE" and ev["total"] == 0 and ev["limitations"]
    q = env.client.get(f"{BASE}/areas/{a.id}/quality-report").json()["report"]
    assert q["real_data_validation"] == "NOT_PERFORMED" and q["validation_status"] == "NOT_VALIDATED" and q["scientifically_validated"] is False


# --- full synthetic run ------------------------------------------------------------------------------
def full_setup(env):
    a = make_area(env)
    seed_dem(env)
    seed_gpm(env)
    seed_external(env)
    seed_events(env)
    seed_insar(env)
    r = env.client.post(f"{BASE}/areas/{a.id}/seismic/refresh", json={"start_date": "2024-01-01", "end_date": "2024-01-31"})
    assert r.status_code == 200 and r.json()["inserted"] == 2
    return a


def test_full_synthetic_run_labels_everything_and_excludes_synthetic_insar(env):
    a = full_setup(env)
    rid = process(env, a)
    run, st = stages(env, rid)
    assert st["DEM"] == "DONE" and st["TERRAIN"] == "DONE" and st["SOIL"] == "DONE" and st["LAND_COVER"] == "DONE"
    assert st["RAINFALL"] == "PARTIAL"  # one missing day -> partial, never silently complete
    assert st["HISTORICAL_LANDSLIDES"] == "DONE" and st["SEISMIC"] == "DONE" and st["INSAR"] == "DONE" and st["QUALITY"] == "DONE"
    assert run["status"] == "PARTIAL"  # the partial rainfall keeps the run honest

    layers = {l["layer_type"]: l for l in env.client.get(f"{BASE}/areas/{a.id}/layers").json()["items"]}
    assert {"ELEVATION", "SLOPE", "ASPECT", "RAINFALL", "SOIL", "LAND_COVER", "HISTORICAL_LANDSLIDES", "SEISMIC"} <= set(layers)
    for l in layers.values():
        assert l["validation_status"] == "NOT_VALIDATED" and l["data_origin"] in ("SYNTHETIC_FIXTURE", "REAL_SATELLITE", "LOCAL_UNVERIFIED")
    assert layers["ELEVATION"]["data_origin"] == "SYNTHETIC_FIXTURE" and "SYNTHETIC" in layers["ELEVATION"]["label"]
    assert layers["SLOPE"]["measurement_kind"] == "DERIVED_MEASUREMENT" and layers["SLOPE"]["units"] == "degree"
    assert layers["ELEVATION"]["has_raster"] and layers["ASPECT"]["has_raster"] and not layers["RAINFALL"]["has_raster"]
    assert all("file_path" not in l and "path" not in l for l in layers.values())
    assert layers["ELEVATION"]["footprint"]["type"] == "Polygon" and layers["ELEVATION"]["crs"] == "EPSG:4326"

    # InSAR: both products referenced and labelled; only the real-labelled test double feeds features
    insar_layers = [l for l in env.client.get(f"{BASE}/layers", params={"area_id": str(a.id)}).json()["items"] if l["layer_type"].startswith("INSAR")]
    assert {l["data_origin"] for l in insar_layers} == {"SYNTHETIC_FIXTURE", "REAL_SATELLITE"}
    assert all(l["provenance"]["validation_status"] == "NOT_VALIDATED" and not l["has_raster"] for l in insar_layers)
    feats = {g["group"]: g for g in env.client.get(f"{BASE}/areas/{a.id}/features").json()["groups"]}
    ins = feats["insar"]
    assert [p["product_type"] for p in ins["values"]["products"]] == ["LOS_VELOCITY"]
    assert [x["data_origin"] for x in ins["values"]["excluded"]] == ["SYNTHETIC_FIXTURE"]
    assert any("sign convention is unverified" in w for w in ins["warnings"])

    # features: descriptive only, lineage kept, never a score
    t = feats["terrain"]
    assert t["status"] == "PROCESSED" and "elevation_mean" in t["values"] and t["units"]["elevation_mean"] == "metre"
    assert t["data_origin"] == "SYNTHETIC_FIXTURE" and t["lineage"]
    def keys(o):  # field NAMES only: the disclaimer prose legitimately says "not a risk score or probability"
        if isinstance(o, dict):
            for k, v in o.items():
                yield str(k).lower()
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)

    names = set(keys(env.client.get(f"{BASE}/areas/{a.id}/features").json()))
    for banned in ("risk", "risk_score", "probability", "susceptibility", "prediction", "score", "forecast"):
        assert not any(banned in n for n in names), banned
    assert feats["historical_landslides"]["values"]["count"] == 1  # the far event is outside the AOI
    assert feats["seismic"]["values"]["count"] == 2
    assert feats["soil"]["status"] == "PROCESSED" and feats["land_cover"]["status"] == "PROCESSED"

    # rainfall: the missing day is a gap, not zero
    rain = env.client.get(f"{BASE}/areas/{a.id}/rainfall").json()
    gap = next(p for p in rain["daily"] if p["date"] == "2024-01-05")
    assert gap["precipitation_mm"] is None and gap["observed"] is False
    assert rain["observed_days"] == 9 and rain["missing_days"] == 1 and rain["units"] == "mm"
    assert rain["monthly"][0]["precipitation_mm"] is None  # January incomplete
    assert all(p["precipitation_mm"] is None for p in rain["rolling"]["7d"][:6])

    q = env.client.get(f"{BASE}/areas/{a.id}/quality-report").json()["report"]
    assert q["contains_synthetic_data"] is True and q["real_data_validation"] == "NOT_PERFORMED"
    assert q["layers"] and q["limitations"] and isinstance(q["passed_checks"], list) and isinstance(q["failed_checks"], list)
    assert (env.root / "processed/environmental" / str(a.id) / "reports" / f"quality_report_{rid}.json").is_file()
    assert (env.root / "processed/environmental" / str(a.id) / "dem" / "slope.tif").is_file()


def test_events_endpoints_return_geojson_inside_the_aoi_only(env):
    a = full_setup(env)
    process(env, a)
    h = env.client.get(f"{BASE}/areas/{a.id}/historical-landslides").json()
    assert h["total"] == 1 and h["geojson"]["features"][0]["properties"]["id"] == "SYN-1"
    assert any("2017-09-28" in x for x in h["limitations"])
    s = env.client.get(f"{BASE}/areas/{a.id}/seismic").json()
    assert s["total"] == 2 and {f["properties"]["id"] for f in s["geojson"]["features"]} == {"us1", "us2"}
    assert any("No causal link" in x for x in s["limitations"])


def test_rerun_skips_identical_inputs_and_force_redoes(env):
    a = full_setup(env)
    process(env, a)
    n_layers = env.db.scalar(select(func.count()).select_from(EnvironmentalLayer))
    run2, st2 = stages(env, process(env, a))
    assert st2["DEM"] == st2["TERRAIN"] == st2["RAINFALL"] == st2["SOIL"] == st2["LAND_COVER"] == "SKIPPED"
    assert st2["FEATURES"] == "DONE"
    feats = {g["group"]: g for g in env.client.get(f"{BASE}/areas/{a.id}/features").json()["groups"]}
    assert feats["terrain"]["status"] == "PROCESSED" and feats["rainfall"]["values"]  # carried over from the earlier run
    assert env.db.scalar(select(func.count()).select_from(EnvironmentalLayer)) < 2 * n_layers  # not all rebuilt
    _, st3 = stages(env, process(env, a, force=True))
    assert st3["DEM"] == "DONE" and st3["TERRAIN"] == "DONE"


def test_stage_subset_and_missing_prerequisite(env):
    a = make_area(env)
    seed_dem(env)
    _, st = stages(env, process(env, a, stages=["DEM", "TERRAIN", "FEATURES"]))
    assert st == {"DEM": "DONE", "TERRAIN": "DONE", "FEATURES": "DONE"}
    b = make_area(env, box(116.001, 5.191, 116.010, 5.199), name="second")
    _, st2 = stages(env, process(env, b, stages=["TERRAIN"]))
    assert st2["TERRAIN"] == "NOT_AVAILABLE"
    assert env.client.post(f"{BASE}/areas/{a.id}/process", json={"stages": ["NOPE"]}).status_code == 422


def test_a_failed_stage_does_not_stop_the_others(env):
    a = make_area(env)
    seed_dem(env, corrupt=True)
    seed_gpm(env, days=3, missing=())
    run, st = stages(env, process(env, a))
    assert st["DEM"] == "FAILED" and st["RAINFALL"] in ("DONE", "PARTIAL") and st["QUALITY"] == "DONE"
    assert run["status"] == "PARTIAL" and "DEM" in run["error_message"]


def test_only_a_dem_is_partial_with_reasons(env):
    a = make_area(env)
    seed_dem(env)
    run, _ = stages(env, process(env, a))
    assert run["status"] == "PARTIAL"
    cov = {i["layer_type"]: i for i in env.client.get(f"{BASE}/areas/{a.id}/coverage").json()["items"]}
    assert cov["ELEVATION"]["available"] and cov["SLOPE"]["available"] and cov["ASPECT"]["available"]
    assert not cov["RAINFALL"]["available"] and "Phase 2 download" in cov["RAINFALL"]["reason"]
    assert "RAINFALL" in env.client.get(f"{BASE}/areas/{a.id}/coverage").json()["missing_datasets"]


def test_area_without_dem_overlap_is_not_available(env):
    a = make_area(env, box(10.0, 10.0, 10.1, 10.1), name="elsewhere")
    seed_dem(env)
    _, st = stages(env, process(env, a))
    assert st["DEM"] == "NOT_AVAILABLE"


# --- raster endpoints ---------------------------------------------------------------------------------
def test_raster_preview_legend_endpoints(env):
    a = full_setup(env)
    process(env, a)
    layers = {l["layer_type"]: l for l in env.client.get(f"{BASE}/areas/{a.id}/layers").json()["items"]}
    for kind, legend_kind in (("ELEVATION", "continuous"), ("SLOPE", "continuous"), ("ASPECT", "circular")):
        lid = layers[kind]["id"]
        png = env.client.get(f"{BASE}/layers/{lid}/preview")
        assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n" and png.headers["x-data-origin"] == "SYNTHETIC_FIXTURE"
        tif = env.client.get(f"{BASE}/layers/{lid}/raster")
        assert tif.status_code == 200 and tif.headers["content-type"] == "image/tiff"
        lg = env.client.get(f"{BASE}/layers/{lid}/legend").json()
        assert lg["kind"] == legend_kind and lg["units"]
        if legend_kind == "continuous":
            assert lg["vmin"] is not None and lg["vmax"] > lg["vmin"] and len(lg["colors"]) == 5
    assert env.client.get(f"{BASE}/layers/{layers['RAINFALL']['id']}/raster").status_code == 404
    lc = env.client.get(f"{BASE}/layers/{layers['LAND_COVER']['id']}/legend").json()
    assert lc["kind"] == "categorical" and lc["classes"][0]["id"] == 10 and lc["classes"][0]["name"] == "Tree cover"


def test_raster_paths_are_confined_and_ids_validated(env):
    a = full_setup(env)
    process(env, a)
    lay = env.db.scalars(select(EnvironmentalLayer).where(EnvironmentalLayer.layer_type == "ELEVATION")).first()
    lay.file_path = "raw/nasadem/20000211__NASADEM_HGT_synthetic.tif"
    env.db.commit()
    for suffix in ("raster", "preview"):
        r = env.client.get(f"{BASE}/layers/{lay.id}/{suffix}")
        assert r.status_code == 404 and "NASADEM" not in r.text
    lay.file_path = "../../etc/passwd"
    env.db.commit()
    assert env.client.get(f"{BASE}/layers/{lay.id}/raster").status_code == 404
    assert env.client.get(f"{BASE}/layers/{uuid.uuid4()}/raster").status_code == 404
    assert env.client.get(f"{BASE}/areas/{uuid.uuid4()}/coverage").status_code == 404
    assert env.client.get(f"{BASE}/processing-runs/{uuid.uuid4()}").status_code == 404
    assert env.client.post(f"{BASE}/areas/{uuid.uuid4()}/process", json={}).status_code == 404


def test_responses_never_expose_filesystem_paths(env):
    a = full_setup(env)
    rid = process(env, a)
    root = str(env.root)
    for url in (f"areas/{a.id}/layers", f"areas/{a.id}/features", f"areas/{a.id}/quality-report", f"processing-runs/{rid}",
                f"areas/{a.id}/rainfall", "datasets", f"areas/{a.id}/coverage"):
        text = env.client.get(f"{BASE}/{url}").text
        assert root not in text and root.replace("\\", "/") not in text, url


# --- run control ---------------------------------------------------------------------------------------
def test_second_active_run_is_a_conflict_and_cancel_works(env):
    a = make_area(env)
    run = env.svc.create_run(env.db, a.id, __import__("app.schemas.environmental", fromlist=["x"]).ProcessConfig())
    r = env.client.post(f"{BASE}/areas/{a.id}/process", json={})
    assert r.status_code == 409
    assert env.client.post(f"{BASE}/processing-runs/{run.id}/cancel").json()["status"] == "CANCELLED"
    env.svc.execute(run.id)  # a cancelled run never executes
    env.db.refresh(run)
    assert run.status == "CANCELLED"
    assert env.client.post(f"{BASE}/processing-runs/{run.id}/cancel").status_code == 409


def test_stale_runs_fail_on_recovery(env):
    a = make_area(env)
    run = env.svc.create_run(env.db, a.id, __import__("app.schemas.environmental", fromlist=["x"]).ProcessConfig())
    assert env.svc.recover_stale_runs() == 1
    env.db.refresh(run)
    assert run.status == "FAILED" and "restart" in run.error_message


def test_process_config_validation(env):
    a = make_area(env)
    for body in ({"start_date": "2024-01-01"}, {"start_date": "2024-02-01", "end_date": "2024-01-01"}, {"rolling_windows": [0]},
                 {"start_date": "2000-01-01", "end_date": "2024-01-01"}):
        assert env.client.post(f"{BASE}/areas/{a.id}/process", json=body).status_code == 422


# --- seismic refresh ---------------------------------------------------------------------------------
def test_seismic_refresh_dedupes_and_reports_upstream_errors(env):
    a = make_area(env)
    body = {"start_date": "2024-01-01", "end_date": "2024-01-31", "min_magnitude": 2.5}
    r1 = env.client.post(f"{BASE}/areas/{a.id}/seismic/refresh", json=body).json()
    assert (r1["fetched"], r1["inserted"], r1["duplicates"]) == (2, 2, 0)
    r2 = env.client.post(f"{BASE}/areas/{a.id}/seismic/refresh", json=body).json()
    assert (r2["inserted"], r2["duplicates"]) == (0, 2)
    assert env.db.scalar(select(func.count()).select_from(EarthquakeEvent)) == 2
    bbox = env.usgs.calls[0][0]
    assert bbox == pytest.approx(AREA.bounds) and env.usgs.calls[0][3] == 2.5
    env.usgs.error = RuntimeError("boom")
    r3 = env.client.post(f"{BASE}/areas/{a.id}/seismic/refresh", json=body)
    assert r3.status_code == 502 and "boom" not in r3.text
    assert env.client.post(f"{BASE}/areas/{a.id}/seismic/refresh", json={"start_date": "2024-02-01", "end_date": "2024-01-01"}).status_code == 422


def test_datasets_catalog_is_honest(env):
    items = env.client.get(f"{BASE}/datasets").json()["items"]
    assert {i["layer_type"] for i in items} >= {"ELEVATION", "RAINFALL", "SOIL", "LAND_COVER", "SEISMIC", "HISTORICAL_LANDSLIDES"}
    assert all(i["implementation_status"] != "IMPLEMENTED_AND_TESTED" for i in items)  # no real file has been processed
    assert any(i["implementation_status"] == "PARTIALLY_IMPLEMENTED" for i in items)


def test_no_network_code_in_pipeline_or_processors():
    """Only the USGS provider may import an HTTP client; the pipeline itself never downloads."""
    import pathlib

    root = pathlib.Path("app/services/environmental")
    for p in root.rglob("*.py"):
        if p.name in ("usgs_earthquake.py",):
            continue
        src = p.read_text(encoding="utf-8")
        for banned in ("import requests", "import httpx", "urllib.request", "earthaccess", "asf_search"):
            assert banned not in src, f"{p}: {banned}"


def test_repeated_per_file_warnings_are_collapsed():
    from app.services.environmental.pipeline.runs import collapse_warnings

    w = [f"d{i}.HDF5: AOI is smaller than an IMERG cell" for i in range(9)] + ["1 of 10 days are missing", "x.h5: only one"]
    out = collapse_warnings(w)
    assert out == ["AOI is smaller than an IMERG cell (9 files)", "1 of 10 days are missing", "x.h5: only one"]
