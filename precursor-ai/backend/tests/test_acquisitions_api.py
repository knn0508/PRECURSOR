from datetime import datetime, timezone

from geoalchemy2.shape import from_shape
from shapely.geometry import shape

from app.models import MonitoredArea, SatelliteAcquisition, SatelliteSource


def test_list_empty(client):
    assert client.get("/api/v1/acquisitions").json() == {"items": [], "total": 0}


def test_list_orders_latest_first_and_limits(client, db, polygon):
    area = MonitoredArea(name="A", geometry=from_shape(shape(polygon), srid=4326))
    src = SatelliteSource(name="Sentinel-1A", provider="ESA", satellite_type="SAR")
    db.add_all([area, src])
    db.commit()
    for day in (1, 2, 3):
        db.add(
            SatelliteAcquisition(
                satellite_source_id=src.id,
                area_id=area.id,
                acquisition_date=datetime(2024, 1, day, tzinfo=timezone.utc),
                polarization="VV",
            )
        )
    db.commit()

    body = client.get("/api/v1/acquisitions?limit=2").json()
    assert body["total"] == 3
    assert [i["acquisition_date"][:10] for i in body["items"]] == ["2024-01-03", "2024-01-02"]
    assert body["items"][0]["satellite_source"] == "Sentinel-1A"
    assert client.get("/api/v1/acquisitions?limit=0").status_code == 422
