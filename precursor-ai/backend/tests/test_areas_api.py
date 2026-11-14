import uuid


def test_list_empty(client):
    r = client.get("/api/v1/areas")
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0}


def test_create_then_get_and_list(client, polygon):
    r = client.post("/api/v1/areas", json={"name": "Demo AOI", "country": "AZ", "geometry": polygon})
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == "Demo AOI"
    assert created["geometry"]["type"] == "Polygon"

    got = client.get(f"/api/v1/areas/{created['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == created["id"]

    listed = client.get("/api/v1/areas").json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == created["id"]


def test_get_unknown_area_404(client):
    r = client.get(f"/api/v1/areas/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_get_bad_uuid_422(client):
    assert client.get("/api/v1/areas/not-a-uuid").status_code == 422


def test_create_rejects_invalid_geometry(client):
    bad_type = client.post("/api/v1/areas", json={"name": "x", "geometry": {"type": "Point", "coordinates": [0, 0]}})
    assert bad_type.status_code == 422
    out_of_range = client.post(
        "/api/v1/areas",
        json={"name": "x", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [200, 0], [200, 10], [0, 0]]]}},
    )
    assert out_of_range.status_code == 422
    assert client.post("/api/v1/areas", json={"geometry": {}}).status_code == 422
