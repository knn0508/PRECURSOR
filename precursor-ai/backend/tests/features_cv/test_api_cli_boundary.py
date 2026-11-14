"""Read-only API, CLI entry point and the ML-boundary scan. SYNTHETIC data only."""
import json
import uuid
from datetime import UTC, datetime

import pandas as pd
import pytest
from geoalchemy2.shape import from_shape
from shapely.geometry import Point, box

from app.core.config import Settings, get_settings
from app.main import app
from app.models import LandslideEvent, MonitoredArea
from app.services.features_cv import __main__ as cli
from app.services.features_cv.dataset import DatasetParams
from app.services.features_cv.dataset_run import run_dataset
from app.services.features_cv.events import load_events
from app.services.features_cv.pipeline import run_extraction
from app.services.features_cv.registry import REGISTRY
from app.services.features_cv.types import forbidden_names
from tests.features_cv.synth import lonlat, write_stack
from tests.features_cv.test_dataset import events_set, params, walk_names

RES = 100.0
N = 96


@pytest.fixture
def env(client, db, tmp_path):
    settings = Settings(data_root=tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    yield type("Env", (), {"client": client, "db": db, "root": tmp_path})
    app.dependency_overrides.pop(get_settings, None)


def make_area(db, area_id=None, bounds=(116.0, 5.0, 116.2, 5.2)):
    a = MonitoredArea(id=area_id, name="synthetic-features-area", geometry=from_shape(box(*bounds), srid=4326))
    db.add(a)
    db.commit()
    return a


BASE = "/api/v1/features-cv"


def test_schema_endpoint_lists_versioned_catalogue_without_data(env):
    r = env.client.get(f"{BASE}/schema")
    assert r.status_code == 200
    j = r.json()
    assert j["feature_schema_version"] == "1.0.0" and j["extractors"] == ["change", "terrain", "texture"]
    names = {f["name"] for f in j["features"]}
    assert {"local_relief_w5", "ndvi_difference", "glcm_ndvi_energy_w16"} <= names
    assert forbidden_names(list(walk_names(j))) == []


def test_manifest_and_summary_404_until_generated_then_200(env):
    a = make_area(env.db)
    for path in (f"{BASE}/areas/{a.id}/features/manifest", f"{BASE}/areas/{a.id}/datasets/summary"):
        r = env.client.get(path)
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert env.client.get(f"{BASE}/areas/{uuid.uuid4()}/features/manifest").status_code == 404
    assert env.client.get(f"{BASE}/areas/not-a-uuid/datasets/summary").status_code in (404, 422)
    area, g, _ = write_stack(env.root, a.id, n=N, res=RES)
    run_extraction(env.root, a.id)
    m = env.client.get(f"{BASE}/areas/{a.id}/features/manifest")
    assert m.status_code == 200
    j = m.json()
    assert j["counts"]["done"] >= 5 and j["contains_synthetic_data"] is True and j["real_data_validation"] == "NOT_PERFORMED" and "local_relief_w5" in {f["name"] for f in j["features"]}
    run_dataset(env.root, a.id, events_set(g), params(), events_origin="SYNTHETIC_FIXTURE")
    s = env.client.get(f"{BASE}/areas/{a.id}/datasets/summary")
    assert s.status_code == 200
    sj = s.json()
    assert sj["counts"]["events_used"] == 8 and sj["leakage"]["ok"] is True and sj["validation_status"] == "NOT_VALIDATED" and sj["caveats"]
    assert "samples" not in json.dumps(sj.get("files", {})) and "path" not in " ".join(sj.keys())  # no file paths exposed


def test_api_has_no_write_or_process_routes_for_phase5(env):
    paths = {p: it for p, it in env.client.get("/openapi.json").json()["paths"].items() if p.startswith("/api/v1/features-cv")}
    assert len(paths) == 3 and all(list(it) == ["get"] for it in paths.values())


def test_events_loader_reads_catalog_rows_inside_the_expanded_area(env):
    a = make_area(env.db)
    env.db.add_all([
        LandslideEvent(external_event_id="IN", event_date=datetime(2015, 5, 1, tzinfo=UTC), geometry=from_shape(Point(116.1, 5.1), srid=4326),
                       original_attributes={"location_accuracy": "1km"}, dataset_version="synthetic-test"),
        LandslideEvent(external_event_id="NEAR", event_date=None, geometry=from_shape(Point(116.3, 5.1), srid=4326), original_attributes={}, dataset_version="synthetic-test"),
        LandslideEvent(external_event_id="FAR", event_date=None, geometry=from_shape(Point(120.0, 5.1), srid=4326), original_attributes={}, dataset_version="synthetic-test"),
    ])
    env.db.commit()
    ev = load_events(env.db, a.id)
    assert [e["id"] for e in ev] == ["IN", "NEAR"]  # FAR is beyond the 0.25 degree margin; NEAR is outside the AOI but still repels background samples
    assert ev[0]["original_attributes"]["location_accuracy"] == "1km" and ev[0]["lon"] == pytest.approx(116.1)
    from app.services.features_cv.types import NotAvailable

    with pytest.raises(NotAvailable):
        load_events(env.db, uuid.uuid4())


def test_cli_extract_and_dataset_end_to_end(env, monkeypatch, capsys):
    from tests.features_cv.synth import grid_dict

    g0 = grid_dict(32650, 600000.0, 630000.0, N, RES)
    (w, n_), (e, s_) = lonlat(g0, 0, 0), lonlat(g0, N - 1, N - 1)  # AOI polygon = the synthetic grid footprint
    a = make_area(env.db, bounds=(min(w, e), min(n_, s_), max(w, e), max(n_, s_)))
    _, g, _ = write_stack(env.root, a.id, n=N, res=RES)
    lon, lat = lonlat(g, 40, 40)
    env.db.add(LandslideEvent(external_event_id="CLI1", event_date=datetime(2016, 1, 1, tzinfo=UTC), geometry=from_shape(Point(lon, lat), srid=4326),
                              original_attributes={"location_accuracy": "exact"}, dataset_version="synthetic-test"))
    env.db.commit()
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(data_root=env.root))
    import app.database.session as sess

    monkeypatch.setattr(sess, "SessionLocal", lambda: env.db.__class__(bind=env.db.get_bind()))
    assert cli.main(["extract", "--area-id", str(a.id)]) == 0
    assert json.loads(capsys.readouterr().out)["features_done"] >= 5
    rc = cli.main(["dataset", "--area-id", str(a.id), "--seed", "3", "--background-ratio", "1", "--block-m", "2000", "--events-origin", "SYNTHETIC_FIXTURE"])
    out = capsys.readouterr()
    assert rc == 0 and "Traceback" not in out.err, out
    summary = json.loads(out.out)
    assert summary["counts"]["events_used"] == 1 and summary["leakage_ok"] is True and summary["synthetic"] is True
    assert cli.main(["extract", "--area-id", str(uuid.uuid4())]) == 2 and "error:" in capsys.readouterr().err


def test_ml_boundary_scan_covers_catalogue_api_schemas_and_manifests(env):
    a = make_area(env.db)
    _, g, _ = write_stack(env.root, a.id, n=N, res=RES)
    fm = run_extraction(env.root, a.id)
    dm = run_dataset(env.root, a.id, events_set(g), params(), events_origin="SYNTHETIC_FIXTURE")
    df = pd.read_parquet(env.root / "processed" / "datasets" / str(a.id) / "samples.parquet")
    names = (list(walk_names(fm)) + list(walk_names(dm)) + list(df.columns) + [s.name for s in REGISTRY.catalogue()]
             + [k for s in REGISTRY.catalogue() for k in s.to_dict()])
    oa = env.client.get("/openapi.json").json()
    for path, item in oa["paths"].items():
        if path.startswith("/api/v1/features-cv"):
            names.append(path)
    for sch, body in oa["components"]["schemas"].items():
        if sch in ("FeatureSchemaRead", "FeaturesManifestRead", "DatasetSummaryRead"):
            names += list(body.get("properties", {}))
    assert forbidden_names(names) == [], forbidden_names(names)
    assert df.dtypes.map(lambda t: str(t)).str.contains("object|str|float|int|bool").all()
    assert DatasetParams.__dataclass_fields__  # the module is importable without any ML dependency
    import importlib.util

    for mod in ("torch", "tensorflow", "sklearn", "xgboost", "lightgbm", "cv2"):
        assert importlib.util.find_spec(mod) is None, f"{mod} must not be installed (ML policy / approved dependencies)"
