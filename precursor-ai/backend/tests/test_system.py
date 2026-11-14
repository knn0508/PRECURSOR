from unittest.mock import MagicMock

from app.database.session import get_db
from app.main import app


def test_system_info(plain_client):
    r = plain_client.get("/api/v1/system/info")
    assert r.status_code == 200
    body = r.json()
    assert body["app_name"] == "PRECURSOR AI"
    assert body["environment"]
    statuses = {m["name"]: m["status"] for m in body["modules"]}
    assert statuses["api"] == "available"
    # Phase 1 must not claim science modules exist.
    assert statuses["data_acquisition"] == "available"
    assert statuses["insar"] == "available"
    assert statuses["risk_assessment"] == "planned"


def test_swagger_and_openapi_available(plain_client):
    assert plain_client.get("/docs").status_code == 200
    paths = plain_client.get("/openapi.json").json()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/areas/{area_id}" in paths


def test_health_degraded_when_db_down(plain_client):
    broken = MagicMock()
    broken.execute.side_effect = RuntimeError("db down")
    app.dependency_overrides[get_db] = lambda: broken
    try:
        r = plain_client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"
    assert r.json()["database"] == "unavailable"


def test_unknown_route_uses_error_envelope(plain_client):
    r = plain_client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "http_error"
