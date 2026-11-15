"""Phase 10 scientific-validation and robustness tests. Geometry is validated against an INDEPENDENT reference (pyproj geodesic
computations on the WGS 84 ellipsoid, hand-known UTM zones). Everything here is analytic or synthetic: it says nothing about real
satellite data. Tolerances are stated next to each assertion."""
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
from pyproj import Geod, Transformer
from shapely.geometry import Polygon, box

import app.core.geo_env  # noqa: F401  (must precede geo libraries)
from app.main import app
from app.services.data_acquisition.aoi import AOI, AOIError
from app.services.environmental.raster.io import inspect_raster
from app.services.environmental.raster.reference_grid import build_reference_grid, choose_projected_crs
from app.services.environmental.types import EnvError
from app.services.insar.inspection import inspect_product

GEOD = Geod(ellps="WGS84")

# (name, lon, lat, expected EPSG). Zones are textbook values, including the Norway exception and the antimeridian side of Fiji.
AOIS = [
    ("Sabah, Malaysia", 116.1, 5.1, 32650), ("Oslo, Norway", 10.7, 59.9, 32632), ("Santiago, Chile", -70.6, -33.4, 32719),
    ("Nairobi, Kenya", 36.8, -1.3, 32737), ("Anchorage, USA", -149.9, 61.2, 32606), ("Svalbard", 15.0, 78.0, 32633),
    ("Fiji (near 180 E)", 179.5, -17.0, 32760), ("McMurdo (polar)", 166.7, -85.5, 3031),
]


@pytest.mark.parametrize("name,lon,lat,epsg", AOIS)
def test_utm_zone_selection_is_correct_on_every_continent(name, lon, lat, epsg):
    assert choose_projected_crs((lon - 0.05, lat - 0.05, lon + 0.05, lat + 0.05)).epsg == epsg, name


@pytest.mark.parametrize("name,lon,lat,epsg", AOIS)
def test_crs_roundtrip_error_below_1e9_degrees(name, lon, lat, epsg):
    fwd, back = Transformer.from_crs(4326, epsg, always_xy=True), Transformer.from_crs(epsg, 4326, always_xy=True)
    x, y = fwd.transform(lon, lat)
    lon2, lat2 = back.transform(x, y)
    assert abs(lon2 - lon) < 1e-9 and abs(lat2 - lat) < 1e-9, name  # tolerance: 1e-9 deg (~0.1 mm)


@pytest.mark.parametrize("name,lon,lat,epsg", [a for a in AOIS if a[3] != 3031])
def test_metric_distance_and_area_in_the_chosen_crs_match_the_ellipsoid(name, lon, lat, epsg):
    """Reference: geodesic length and area on WGS 84. Tolerance: 0.1 % for a 10 km line and 0.2 % for a 0.1 x 0.1 degree box,
    which covers the UTM scale factor (0.9996 at the central meridian, up to ~1.001 at the zone edge)."""
    fwd = Transformer.from_crs(4326, epsg, always_xy=True)
    lon2 = lon + 0.09 / max(math.cos(math.radians(lat)), 0.2)
    _, _, d_geod = GEOD.inv(lon, lat, lon2, lat)
    (x1, y1), (x2, y2) = fwd.transform(lon, lat), fwd.transform(lon2, lat)
    d_utm = math.hypot(x2 - x1, y2 - y1)
    assert abs(d_utm - d_geod) / d_geod < 1e-3, (name, d_utm, d_geod)
    ring = [(lon, lat), (lon + 0.1, lat), (lon + 0.1, lat + 0.1), (lon, lat + 0.1)]
    a_geod = abs(GEOD.polygon_area_perimeter([p[0] for p in ring], [p[1] for p in ring])[0])
    pts = [fwd.transform(*p) for p in ring]
    a_utm = abs(Polygon(pts).area)
    assert abs(a_utm - a_geod) / a_geod < 2e-3, (name, a_utm, a_geod)


@pytest.mark.parametrize("name,lon,lat,epsg", AOIS)
def test_reference_grid_builds_in_the_expected_crs(name, lon, lat, epsg):
    g = build_reference_grid(box(lon - 0.05, lat - 0.05, lon + 0.05, lat + 0.05), resolution_m=100.0)
    assert g.epsg == epsg and g.grid.width > 10 and g.grid.height > 10, name


def test_antimeridian_aois_are_rejected_not_wrapped():
    with pytest.raises(EnvError, match="antimeridian"):
        build_reference_grid((179.0, -17.0, -179.0, -16.0))  # west > east
    with pytest.raises(AOIError):
        AOI.from_geometry("x", Polygon([(179, 0), (181, 0), (181, 1), (179, 1)]))  # coordinates beyond 180


# Slope on a known plane (projected exact; geographic at two latitudes) is already validated against analytic planes in
# tests/environmental/test_terrain_slope_aspect.py; not duplicated here.


# ---- robustness: corrupt and missing inputs fail cleanly -------------------------------------
def test_corrupt_and_empty_files_fail_cleanly(tmp_path: Path):
    bad, empty = tmp_path / "bad.tif", tmp_path / "empty.tif"
    bad.write_bytes(b"not a tiff\x00\x01garbage")
    empty.write_bytes(b"")
    for f in (bad, empty):
        with pytest.raises(EnvError, match="cannot be opened as a raster"):
            inspect_raster(f)
    h5 = tmp_path / "bad.h5"
    h5.write_bytes(b"\x89HDF-garbage")
    rep = inspect_product(h5)  # reports, does not crash
    assert any("unsupported or unrecognised" in w for w in (rep.warnings or []) + list(getattr(rep, "errors", []) or []))
    with pytest.raises(FileNotFoundError):
        inspect_product(tmp_path / "missing.h5")


def test_oversize_aoi_is_refused():
    aoi = AOI.from_geometry("big", box(0, 0, 20, 20))
    with pytest.raises(AOIError, match="limit"):
        aoi.validate_size(5.0)


# ---- load and concurrency (smoke level; generous bounds, measured values are recorded in the validation report) ------
def test_concurrent_health_requests_all_succeed(plain_client):
    from fastapi.testclient import TestClient

    def hit(_):
        return TestClient(app).get("/api/v1/health").status_code

    t0 = time.perf_counter()
    with ThreadPoolExecutor(16) as ex:
        codes = list(ex.map(hit, range(64)))
    assert set(codes) == {200}
    assert time.perf_counter() - t0 < 30


def test_db_bbox_query_over_many_events_is_fast(client, db):
    from datetime import UTC, datetime

    from geoalchemy2.shape import from_shape
    from shapely.geometry import Point

    from app.models import LandslideEvent
    rng = np.random.default_rng(0)
    rows = [LandslideEvent(external_event_id=f"load-{i}", event_date=datetime(2010, 1, 1, tzinfo=UTC), country="Testland",
                           geometry=from_shape(Point(float(x), float(y)), srid=4326), original_attributes={"synthetic": True}, dataset_version="load-test")
            for i, (x, y) in enumerate(zip(rng.uniform(-170, 170, 3000), rng.uniform(-60, 60, 3000)))]
    db.add_all(rows)
    db.commit()
    t0 = time.perf_counter()
    r = client.get("/api/v1/data/landslide-events", params={"bbox": "-10,-10,10,10", "limit": 1000})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200 and r.json()["total"] >= 1
    assert elapsed < 5.0, elapsed


def test_error_envelope_is_consistent_across_error_kinds(plain_client):
    for path, code in (("/api/v1/does-not-exist", 404), ("/api/v1/areas/not-a-uuid", 422)):
        r = plain_client.get(path)
        assert r.status_code == code
        body = r.json()
        assert set(body) == {"error"} and {"code", "message"} <= set(body["error"]), body
    assert json.dumps(plain_client.get("/api/v1/health").json())  # health is plain JSON
