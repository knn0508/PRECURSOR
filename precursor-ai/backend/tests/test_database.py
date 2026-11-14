from datetime import datetime, timezone

from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy import text

from app.models import MonitoredArea, SatelliteAcquisition, SatelliteSource
from app.repositories.area_repository import AreaRepository
from app.repositories.satellite_repository import (
    SatelliteAcquisitionRepository,
    SatelliteSourceRepository,
)


def test_connectivity_and_postgis(db):
    assert db.execute(text("SELECT 1")).scalar() == 1
    assert db.execute(text("SELECT PostGIS_Version()")).scalar()


def test_health_endpoint_reports_connected(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "app_name": "PRECURSOR AI",
        "version": "0.1.0",
        "database": "connected",
    }


def test_models_roundtrip_and_relations(db, polygon):
    area = AreaRepository(db).add(
        MonitoredArea(name="Test AOI", geometry=from_shape(shape(polygon), srid=4326))
    )
    source = SatelliteSourceRepository(db).add(
        SatelliteSource(name="Sentinel-1A", provider="ESA", satellite_type="SAR")
    )
    acq = SatelliteAcquisitionRepository(db).add(
        SatelliteAcquisition(
            satellite_source_id=source.id,
            area_id=area.id,
            acquisition_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            metadata_={"relative_orbit": 123},
        )
    )
    assert area.area_type == "landslide_susceptible"
    assert area.created_at is not None
    assert source.is_active is True
    assert acq.processing_status == "pending"
    assert acq.metadata_ == {"relative_orbit": 123}
    assert acq.area.id == area.id and acq.source.name == "Sentinel-1A"
    # Spatial query works (PostGIS function on stored geometry).
    contains = db.execute(
        text("SELECT ST_Contains(geometry, ST_SetSRID(ST_MakePoint(44.05, 40.05), 4326)) FROM monitored_areas")
    ).scalar()
    assert contains is True


def test_repository_crud(db, polygon):
    repo = AreaRepository(db)
    area = repo.add(MonitoredArea(name="A", geometry=from_shape(shape(polygon), srid=4326)))
    assert repo.get(area.id).name == "A"
    assert repo.count() == 1
    repo.delete(area)
    assert repo.get(area.id) is None
    assert repo.list() == []
