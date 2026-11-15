"""ML slot tests (ADR-0008). TestDouble below lives in tests only and is never importable from app code."""
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.v1.prediction import get_prediction_service
from app.core.config import Settings, get_settings
from app.main import app
from app.schemas import prediction as sch
from app.schemas.prediction import CalibrationInfo, RiskModelInput, RiskModelOutput, ValidTime
from app.services.features_cv.types import forbidden_names
from app.services.prediction.predictor import ModelNotTrained, NullPredictor, Predictor
from app.services.prediction.registry import ModelRegistry
from app.services.prediction.service import PredictionService

AREA = uuid.uuid4()
SPEC = {"feature_names": ["local_relief_w5"], "feature_schema_version": "1.0.0", "grid_crs": "EPSG:32650", "grid_resolution_m": 30.0}


def write_model(root: Path, folder="m1", version="1.0.0", **over) -> Path:
    d = root / folder / version
    d.mkdir(parents=True)
    meta = {"model_id": folder, "version": version, "heads": ["susceptibility"], "model_card": "MODEL_CARD.md",
            "training_data_provenance": {"inventory": "TEST_FIXTURE"}, "valid_region": {"type": "Polygon", "coordinates": []},
            "valid_time": {"start": "2020-01-01T00:00:00Z"}, "input_spec": SPEC}
    meta.update(over)
    (d / "metadata.json").write_text(json.dumps({k: v for k, v in meta.items() if v is not None}))
    (d / "MODEL_CARD.md").write_text("TEST_FIXTURE card")
    return d


class TestDouble:
    """TEST_DOUBLE: returns a constant; proves the swap path only. Never importable from app code."""
    __test__ = False
    model_id, version, heads = "m1", "1.0.0", ("susceptibility",)

    def predict(self, model_input, features_manifest):
        return RiskModelOutput(model_id=self.model_id, model_version=self.version, head=model_input.head, area_id=model_input.area_id,
                               probability=0.5, calibration=CalibrationInfo(calibrated=False), training_data_provenance={"TEST_DOUBLE": True},
                               valid_region={}, valid_time=ValidTime(start=datetime(2020, 1, 1, tzinfo=UTC)))


def override(svc):
    app.dependency_overrides[get_prediction_service] = lambda: svc
    return svc


@pytest.fixture(autouse=True)
def _clean():
    yield
    app.dependency_overrides.pop(get_prediction_service, None)


def test_default_backend_is_none():
    assert Settings(_env_file=None).prediction_backend == "none"


@pytest.mark.parametrize("path", ["/api/v1/prediction/susceptibility", "/api/v1/prediction/trigger"])
def test_none_backend_returns_model_not_trained(plain_client, tmp_path, path):
    override(PredictionService("none", ModelRegistry(tmp_path), tmp_path))
    r = plain_client.post(path, json={"area_id": str(AREA)})
    assert r.status_code == 200 and r.json()["status"] == "MODEL_NOT_TRAINED" and r.json()["output"] is None


def test_status_and_models_under_none(plain_client, tmp_path):
    override(PredictionService("none", ModelRegistry(tmp_path), tmp_path))
    assert plain_client.get("/api/v1/prediction/status").json()["status"] == "MODEL_NOT_TRAINED"
    assert plain_client.get("/api/v1/prediction/models").json() == {"registered": [], "refused": []}


def test_null_predictor_never_scores():
    assert isinstance(NullPredictor(), Predictor)
    with pytest.raises(ModelNotTrained):
        NullPredictor().predict(None, {})


def test_registry_accepts_complete_and_refuses_incomplete(tmp_path):
    write_model(tmp_path, "good")
    write_model(tmp_path, "nocard").joinpath("MODEL_CARD.md").unlink()
    write_model(tmp_path, "noprov", training_data_provenance=None)
    write_model(tmp_path, "noregion", valid_region=None)
    write_model(tmp_path, "notime", valid_time=None)
    write_model(tmp_path, "scorey", input_spec={"feature_names": ["landslide_probability"]})
    write_model(tmp_path, "_template")  # ignored
    reg = ModelRegistry(tmp_path)
    assert [e.model_id for e in reg.entries] == ["good"]
    assert sorted(r.path.split("/")[0] for r in reg.refused) == ["nocard", "noprov", "noregion", "notime", "scorey"]


def test_registry_refuses_id_folder_mismatch(tmp_path):
    write_model(tmp_path, "a", model_id="b")
    assert ModelRegistry(tmp_path).entries == []


def test_attach_requires_registered_entry(tmp_path):
    with pytest.raises(Exception, match="not a registered"):
        ModelRegistry(tmp_path).attach("x", "1", TestDouble())


def test_input_wraps_model_input_spec():
    RiskModelInput(head="trigger", area_id=AREA, input_spec=SPEC, horizon_days=3)
    with pytest.raises(ValidationError):
        RiskModelInput(head="trigger", area_id=AREA, input_spec={"feature_names": []})
    with pytest.raises(ValidationError):
        RiskModelOutput(model_id="a", model_version="1", head="trigger", area_id=AREA, probability=1.5, calibration=CalibrationInfo(calibrated=False),
                        training_data_provenance={}, valid_region={}, valid_time=ValidTime(start=datetime.now(UTC)))


def test_swap_path_with_test_double(plain_client, tmp_path, monkeypatch):
    """Same routes and schema; only the answer changes once a predictor is attached."""
    write_model(tmp_path / "models")
    reg = ModelRegistry(tmp_path / "models")
    reg.attach("m1", "1.0.0", TestDouble())
    override(PredictionService("registered_model", reg, tmp_path))
    manifest = {"feature_schema_version": "1.0.0", "features": [{"name": "local_relief_w5", "status": "DONE"}],
                "grid": {"crs": "EPSG:32650", "resolution_m": 30.0}}
    monkeypatch.setattr("app.services.prediction.service.read_features_manifest", lambda root, area: manifest)
    body = {"area_id": str(AREA)}
    r = plain_client.post("/api/v1/prediction/susceptibility", json=body)
    assert r.status_code == 200 and r.json()["status"] == "OK" and r.json()["output"]["probability"] == 0.5
    assert plain_client.get("/api/v1/prediction/status").json()["status"] == "OK"
    assert plain_client.post("/api/v1/prediction/trigger", json=body).json()["status"] == "MODEL_NOT_TRAINED"  # head not served
    manifest["grid"]["resolution_m"] = 10.0  # incompatible data is refused, not silently resampled
    assert plain_client.post("/api/v1/prediction/susceptibility", json=body).status_code == 422


def test_app_code_boundary():
    names = [n for m in (RiskModelInput, sch.PredictionResponse, sch.PredictionStatus, sch.ModelRegistryEntry, sch.PredictionRequest) for n in m.model_fields]
    assert not forbidden_names(names)
    app_dir = Path(__file__).resolve().parents[2] / "app"
    assert not [p for p in app_dir.rglob("*.py") if "TEST_DOUBLE" in p.read_text(encoding="utf-8")]


def test_default_service_rescans_models_and_keeps_attached_predictors(plain_client, tmp_path):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, prediction_backend="registered_model", models_dir=tmp_path / "m", data_root=tmp_path)
    try:
        assert plain_client.get("/api/v1/prediction/models").json()["registered"] == []
        write_model(tmp_path / "m")  # added while the app runs
        assert [e["model_id"] for e in plain_client.get("/api/v1/prediction/models").json()["registered"]] == ["m1"]
    finally:
        app.dependency_overrides.pop(get_settings, None)
