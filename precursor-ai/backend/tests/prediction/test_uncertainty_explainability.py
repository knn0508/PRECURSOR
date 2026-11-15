"""Phase 8 tests: schemas, mask determinism, propagation vs hand-computed values, ledger, reliability, MODEL_NOT_AVAILABLE.
All inputs are synthetic or hand-made; passing says nothing about real data."""
import json
import math
import uuid
from datetime import UTC, datetime

import numpy as np
import pytest
from pydantic import ValidationError

from app.api.v1.prediction import get_prediction_service
from app.core.config import Settings, get_settings
from app.main import app
from app.schemas import uncertainty as sch
from app.schemas.uncertainty import Explanation, FeatureContribution, UncertaintyReport
from app.services.features_cv.pipeline import MANIFEST_NAME
from app.services.features_cv.types import forbidden_names
from app.services.prediction.explainer import Explainer
from app.services.prediction.registry import ModelRegistry, RegistryError
from app.services.prediction.service import PredictionService
from app.services.uncertainty import masks, propagation
from app.services.uncertainty.ledger import apply_suppression, build_report
from app.services.uncertainty.reliability import suppression_reasons
from tests.prediction.test_prediction_slot import AREA, write_model

MANIFEST = {"contains_synthetic_data": True, "real_data_validation": "NOT_PERFORMED", "counts": {"done": 3, "not_available": 2},
            "grid": {"crs": "EPSG:32650", "resolution_m": 30.0}, "input_layers": [{"layer_type": "SMAP_SOIL_MOISTURE"}, {"layer_type": "ELEVATION"}],
            "skipped_layers": [], "features": []}


@pytest.fixture(autouse=True)
def _clean():
    yield
    app.dependency_overrides.clear()


# ---------------- propagation (hand computed) ----------------
def test_phase_std_matches_hand_computation():
    # gamma=0.5, N=1: sqrt(1-0.25)/0.5/sqrt(2) = sqrt(1.5)
    assert propagation.phase_std_rad(np.array([0.5]), 1)[0] == pytest.approx(math.sqrt(1.5), rel=1e-12)
    assert propagation.phase_std_rad(np.array([1.0]), 4)[0] == 0.0
    assert propagation.phase_std_rad(np.array([0.5]), 8)[0] == pytest.approx(math.sqrt(1.5) / math.sqrt(8), rel=1e-12)


def test_los_displacement_std_hand_computed():
    # lambda = 0.24 m: 0.24 / (4 pi) * sqrt(1.5) = 0.0233909... m
    assert propagation.los_displacement_std_m(np.array([0.5]), 1, 0.24)[0] == pytest.approx(0.24 / (4 * math.pi) * math.sqrt(1.5), rel=1e-12)
    assert propagation.los_displacement_std_m(np.array([0.5]), 1, 0.24)[0] == pytest.approx(0.0233909, abs=1e-7)


def test_propagation_missing_and_invalid_are_not_estimated():
    out = propagation.phase_std_rad(np.array([0.0, np.nan, 1.2, -0.1]), 1)
    assert np.isnan(out).all()  # never 0 or a made-up value
    with pytest.raises(ValueError):
        propagation.phase_std_rad(np.array([0.5]), 0)
    with pytest.raises(ValueError):
        propagation.los_displacement_std_m(np.array([0.5]), 1, 5.0)  # wavelength out of range


# ---------------- masks (deterministic, hand-made geometry) ----------------
def test_threshold_masks_flag_nan():
    assert masks.low_coherence_mask(np.array([0.1, 0.5, np.nan]), 0.3).tolist() == [True, False, True]
    assert masks.vegetation_mask(np.array([0.2, 0.8, np.nan]), 0.6).tolist() == [False, True, True]


def test_layover_shadow_geometry():
    # sensor looks east (az 90), so it sits to the west: slopes facing west (aspect 270) face the sensor. incidence 40.
    slope = np.array([60.0, 30.0, 60.0, 0.0, 60.0, np.nan])
    aspect = np.array([270.0, 270.0, 90.0, 0.0, 0.0, 10.0])
    lay, sh = masks.layover_shadow_masks(slope, aspect, 90.0, 40.0)
    assert lay.tolist() == [True, False, False, False, False, True]  # 60 >= 40 layover; 30 < 40 not; NaN flagged
    assert sh.tolist() == [False, False, True, False, False, True]  # facing away by 60 >= 90-40 -> shadow; flat/perpendicular not
    lay2, sh2 = masks.layover_shadow_masks(slope, aspect, 90.0, 40.0)
    assert (lay == lay2).all() and (sh == sh2).all()  # deterministic


def test_los_sensitivity_hand_computed():
    # hand: slope 45 facing the sensor: east term (-sin40)(-cos45)... gives -0.0872 after adding the vertical term cos40*(-sin45)
    s = masks.los_sensitivity(np.array([45.0, 45.0, 0.0]), np.array([270.0, 90.0, 123.0]), 90.0, 40.0)
    assert s[0] == pytest.approx(-0.0872, abs=1e-4)
    assert s[1] == pytest.approx(-0.9962, abs=1e-4)  # moving away from the sensor and down: range grows, sign negative
    assert np.isnan(s[2])  # flat: aspect undefined, so no downslope direction (flagged by the mask, never a number)
    ins = masks.los_insensitive_mask(np.array([45.0, 45.0]), np.array([270.0, 90.0]), 90.0, 40.0, 0.2)
    assert ins.tolist() == [True, False]
    assert masks.los_insensitive_mask(np.array([0.0]), np.array([0.0]), 90.0, 40.0, 0.2).tolist() == [True]


# ---------------- ledger ----------------
def test_ledger_reports_only_recorded_facts():
    r = build_report(AREA, MANIFEST, insar_quality={"sign_convention_verified": False, "data_origin": "SYNTHETIC_FIXTURE", "coherence": {"mean": 0.42}},
                     series_quality={"RAINFALL": {"expected_days": 10, "missing_days": 2}})
    codes = {i.code for i in r.items}
    assert {"SYNTHETIC_INPUTS", "REAL_DATA_NOT_VALIDATED", "FEATURES_NOT_AVAILABLE", "RESOLUTION_MISMATCH", "TEMPORAL_GAPS",
            "SIGN_CONVENTION_UNVERIFIED", "INSAR_SYNTHETIC", "INSAR_COHERENCE_MEAN"} <= codes
    by = {i.code: i for i in r.items}
    assert by["TEMPORAL_GAPS"].value == pytest.approx(20.0) and by["RESOLUTION_MISMATCH"].value == pytest.approx(300.0)  # 9000 m / 30 m
    assert by["INSAR_COHERENCE_MEAN"].value == 0.42
    assert r.predictive_uncertainty == "NOT_ESTIMATED"
    assert all(i.code != "RESOLUTION_MISMATCH" or "ELEVATION" not in i.message for i in r.items)  # 30 m DEM on a 30 m grid is not flagged


def test_ledger_skipped_layer_message():
    r = build_report(AREA, {**MANIFEST, "skipped_layers": [{"layer": "SOIL", "reason": "no file"}]})
    assert [i.message for i in r.items if i.code == "LAYER_SKIPPED"] == ["Layer SOIL was skipped: no file."]


def test_ledger_clean_manifest_has_no_synthetic_item():
    clean = {**MANIFEST, "contains_synthetic_data": False, "real_data_validation": "PERFORMED", "counts": {"not_available": 0}, "input_layers": []}
    assert build_report(AREA, clean).items == []


def test_schema_validation_and_boundary():
    with pytest.raises(ValidationError):
        UncertaintyReport(area_id=AREA, items=[], notes=[], predictive_uncertainty="HIGH")
    with pytest.raises(ValidationError):
        sch.UncertaintyItem(code="x", source_phase=3, severity="CRITICAL", message="m")
    names = [n for m in (sch.UncertaintyReport, sch.UncertaintyItem, sch.ExplainRequest, sch.ExplainResponse, sch.Explanation) for n in m.model_fields]
    assert not forbidden_names([n for n in names if n != "predictive_uncertainty"])


# ---------------- reliability ----------------
def test_suppression_reasons():
    ok = suppression_reasons(valid_region_bbox=(0, 0, 10, 10), valid_time={"start": "2020-01-01T00:00:00Z"}, point=(5, 5),
                             when=datetime(2021, 1, 1, tzinfo=UTC), valid_fraction=0.9, min_valid_fraction=0.5, synthetic_inputs=False)
    assert ok == []
    bad = suppression_reasons(valid_region_bbox=(0, 0, 10, 10), valid_time={"start": "2020-01-01T00:00:00Z", "end": "2020-12-31T00:00:00Z"},
                              point=(50, 5), when=datetime(2021, 1, 1, tzinfo=UTC), valid_fraction=None, min_valid_fraction=0.5, synthetic_inputs=True)
    assert {r.code for r in bad} == {"OUTSIDE_VALID_REGION", "OUTSIDE_VALID_TIME", "INSUFFICIENT_COVERAGE", "SYNTHETIC_INPUTS"}
    rep = apply_suppression(build_report(AREA, MANIFEST), bad)
    assert rep.suppressed and len(rep.suppression_reasons) == 4


# ---------------- API ----------------
def test_uncertainty_endpoint(plain_client, tmp_path):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, data_root=tmp_path)
    assert plain_client.get(f"/api/v1/uncertainty/areas/{AREA}/report").status_code == 404  # no feature run, no report
    d = tmp_path / "processed" / "features" / str(AREA)
    d.mkdir(parents=True)
    (d / MANIFEST_NAME).write_text(json.dumps(MANIFEST))
    r = plain_client.get(f"/api/v1/uncertainty/areas/{AREA}/report")
    assert r.status_code == 200 and r.json()["predictive_uncertainty"] == "NOT_ESTIMATED"
    assert any(i["code"] == "SYNTHETIC_INPUTS" for i in r.json()["items"])


# ---------------- explainer: MODEL_NOT_AVAILABLE and swap path ----------------
class TestExplainer:
    """TEST_DOUBLE explainer: constant contribution, tests only."""
    __test__ = False
    model_id, version = "m1", "1.0.0"

    def explain(self, model_input, features_manifest, scope, cell):
        return Explanation(model_id="m1", model_version="1.0.0", head=model_input.head, scope=scope, method="TEST_DOUBLE",
                           background_dataset_ref="TEST_FIXTURE", contributions=[FeatureContribution(feature="local_relief_w5", contribution=0.0)], cell=cell)


def _explain(client, body=None):
    return client.post("/api/v1/prediction/explain", json=body or {"area_id": str(AREA), "head": "susceptibility"})


def test_explain_model_not_available_under_none(plain_client, tmp_path):
    app.dependency_overrides[get_prediction_service] = lambda: PredictionService("none", ModelRegistry(tmp_path), tmp_path)
    r = _explain(plain_client)
    assert r.status_code == 200 and r.json()["status"] == "MODEL_NOT_AVAILABLE" and r.json()["explanation"] is None


def test_registered_model_without_explainer_is_not_available(plain_client, tmp_path):
    write_model(tmp_path / "models")
    app.dependency_overrides[get_prediction_service] = lambda: PredictionService("registered_model", ModelRegistry(tmp_path / "models"), tmp_path)
    assert _explain(plain_client).json()["status"] == "MODEL_NOT_AVAILABLE"


def test_explainer_json_validation(tmp_path):
    d = write_model(tmp_path)
    (d / "explainer.json").write_text(json.dumps({"method": "m", "scopes": ["global"]}))  # no background dataset ref
    reg = ModelRegistry(tmp_path)
    assert len(reg.entries) == 1 and any("explainer.json" in r.path for r in reg.refused)
    with pytest.raises(RegistryError):
        reg.attach_explainer("m1", "1.0.0", TestExplainer())


def test_explainer_swap_path(plain_client, tmp_path, monkeypatch):
    d = write_model(tmp_path / "models")
    (d / "explainer.json").write_text(json.dumps({"method": "TEST_DOUBLE", "background_dataset_ref": "TEST_FIXTURE", "scopes": ["global"]}))
    reg = ModelRegistry(tmp_path / "models")
    reg.attach_explainer("m1", "1.0.0", TestExplainer())
    assert isinstance(TestExplainer(), Explainer)
    app.dependency_overrides[get_prediction_service] = lambda: PredictionService("registered_model", reg, tmp_path)
    manifest = {"feature_schema_version": "1.0.0", "features": [{"name": "local_relief_w5", "status": "DONE"}], "grid": {"crs": "EPSG:32650", "resolution_m": 30.0}}
    monkeypatch.setattr("app.services.prediction.service.read_features_manifest", lambda root, area: manifest)
    r = _explain(plain_client)
    assert r.json()["status"] == "OK" and r.json()["explanation"]["caveats"] == ["Describes model behaviour, not physical causation."]
    assert _explain(plain_client, {"area_id": str(AREA), "head": "susceptibility", "scope": "local"}).status_code == 422  # unsupported scope
    assert _explain(plain_client, {"area_id": str(AREA), "head": "trigger"}).json()["status"] == "MODEL_NOT_AVAILABLE"  # head not served


def test_no_explainer_in_app_code():
    from pathlib import Path
    src = "\n".join(p.read_text(encoding="utf-8") for p in (Path(__file__).resolve().parents[2] / "app").rglob("*.py"))
    import re
    assert not re.search(r"^\s*(import|from)\s+(shap|lime)", src, re.M) and "TEST_DOUBLE" not in src
