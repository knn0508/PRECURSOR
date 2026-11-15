"""Bundle API on the real copied bundle in <repo>/data (read-only). No DB needed."""
from pathlib import Path

import pytest

from app.core.config import Settings, get_settings
from app.main import app

DATA = Path(__file__).resolve().parents[3] / "data"
pytestmark = pytest.mark.skipif(not (DATA / "displacement_forecast" / "artifacts" / "forecast.tif").exists(), reason="bundle absent")
U = "/api/v1/displacement-forecast"


@pytest.fixture
def c(plain_client):
    app.dependency_overrides[get_settings] = lambda: Settings(data_root=DATA)
    yield plain_client
    app.dependency_overrides.pop(get_settings, None)


def test_status_labelled(c):
    j = c.get(f"{U}/status").json()
    assert j["available"] and "NOT A WARNING" in j["label"] and j["provenance"]["horizon_days"] == 12.0


def test_status_reports_reproduction_when_present(c):
    j = c.get(f"{U}/status").json()
    if (DATA / "displacement_forecast" / "artifacts" / "reproduction.json").exists():
        assert j["reproduction"]["nan_pattern_equal"] is True and j["reproduction"]["max_abs_diff_mm"] < 0.01
    else:
        assert j["reproduction"] is None


def test_metrics_honest(c):
    j = c.get(f"{U}/metrics").json()
    assert j["best_naive_mae"] > 0 and any(r["model"] == "lstm_tcn" for r in j["benchmark"])
    assert j["verification"]["ground_truth_coverage"]["published_JPL_UAVSAR_SepOct2024_mm_day"] == 14.5


def test_forecast_grid_nulls_and_quantile_order(c):
    j = c.get(f"{U}/forecast").json()
    b = j["bands"]
    assert j["height"] == len(b["q50_mm"]) and j["width"] == len(b["q50_mm"][0])
    tl, tr, br, bl = j["corners"]
    assert tl[1] > bl[1] and tr[0] > tl[0] and abs(tl[1] - tr[1]) > 1e-4   # north up, east right, grid slightly rotated vs lon/lat
    assert 0 < j["no_estimate_share"] < 1 and -119 < j["bounds"]["west"] < j["bounds"]["east"] < -118
    for lo, md, hi in zip(b["q10_mm"], b["q50_mm"], b["q90_mm"]):
        for x, y, z in zip(lo, md, hi):
            if y is not None:
                assert x <= y <= z


def test_files_and_unknown(c):
    assert c.get(f"{U}/images/forecast_map").headers["content-type"] == "image/png"
    assert c.get(f"{U}/docs/limitations_v2").status_code == 200
    assert c.get(f"{U}/images/nope").status_code == 404
    assert c.get(f"{U}/docs/nope").status_code == 404
