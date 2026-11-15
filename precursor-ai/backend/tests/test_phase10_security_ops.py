"""Phase 10 checks on security, ML-slot integrity and deployment files. These read repository files, so they fail if a weight file,
a real secret or a root container ever ships."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEIGHT_SUFFIXES = {".pt", ".pth", ".onnx", ".pkl", ".pickle", ".joblib", ".ckpt", ".safetensors", ".bin", ".npz", ".npy", ".h5", ".hdf5", ".keras", ".pb", ".tflite", ".xgb", ".lgb"}


def test_no_model_weights_or_registered_models_ship():
    models = REPO / "models"
    files = [p for p in models.rglob("*") if p.is_file()]
    assert not [p for p in files if p.suffix.lower() in WEIGHT_SUFFIXES], "a weight/artifact file is committed under models/"
    assert not [p for p in files if p.name == "metadata.json"], "a registered model's metadata.json ships; only templates may"
    assert not [p for p in (REPO / "ai_engine").rglob("*") if p.suffix.lower() in WEIGHT_SUFFIXES]


def test_prediction_backend_default_is_none_and_every_route_says_not_trained(plain_client):
    from app.core.config import Settings
    assert Settings(_env_file=None).prediction_backend == "none"
    body = {"area_id": "00000000-0000-0000-0000-000000000001"}
    for head in ("susceptibility", "trigger"):
        r = plain_client.post(f"/api/v1/prediction/{head}", json=body)
        assert r.status_code == 200 and r.json()["status"] == "MODEL_NOT_TRAINED" and r.json()["output"] is None
        e = plain_client.post("/api/v1/prediction/explain", json={**body, "head": head})
        assert e.json()["status"] == "MODEL_NOT_AVAILABLE" and e.json()["explanation"] is None
    assert plain_client.get("/api/v1/prediction/status").json()["status"] == "MODEL_NOT_TRAINED"


def test_env_example_holds_no_real_secrets_and_env_is_ignored():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    for key in ("EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"):
        m = re.search(rf"^{key}=(.*)$", text, re.M)
        assert m is not None and m.group(1).strip() in ("", "your-username", "your-password"), f"{key} in .env.example must be empty/placeholder"
    assert re.search(r"^POSTGRES_PASSWORD=(change-me.*|)$", text, re.M)
    assert re.search(r"^\.env$", (REPO / ".gitignore").read_text(encoding="utf-8"), re.M)


def test_containers_run_as_non_root():
    backend = (REPO / "backend" / "Dockerfile").read_text(encoding="utf-8")
    frontend = (REPO / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^USER\s+(?!root)\S+", backend, re.M) and re.search(r"^USER\s+(?!root)\S+", frontend, re.M)
    assert "python:3.12-slim" in backend and "alpine" in frontend  # minimal base images


def test_cors_allows_only_configured_origins(plain_client):
    ok = plain_client.options("/api/v1/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    evil = plain_client.options("/api/v1/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in evil.headers


def test_error_responses_do_not_leak_stack_traces(plain_client):
    r = plain_client.post("/api/v1/areas", json={"name": "x", "geometry": {"type": "Polygon", "coordinates": "garbage"}})
    assert r.status_code in (400, 422)
    text = r.text
    assert "Traceback" not in text and "site-packages" not in text


def test_health_reports_database_state(plain_client):
    r = plain_client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] in ("ok", "degraded") and "database" in r.json()
