"""Distance-to-river/fault/road: numerical oracles in a metric grid. SYNTHETIC inputs only."""
import app.core.geo_env  # noqa: F401

import json

import numpy as np
import pytest
import rasterio
from affine import Affine
from pyproj import Geod, Transformer

from app.services.environmental.distances.distance_processor import process_distance
from app.services.environmental.external_synthetic import make_vector_geojson, synthetic_grid
from app.services.environmental.features.distance_features import distance_features
from app.services.environmental.raster.alignment import TargetGrid
from app.services.environmental.types import DataOrigin, EnvError, LayerKind, LayerStatus, NotAvailable

LON, LAT = 117.0, 5.9  # UTM 50N (EPSG:32650)


def gj(path, geoms, crs=None):
    doc = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": g} for g in geoms]}
    if crs:
        doc["crs"] = {"type": "name", "properties": {"name": crs}}
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def px(grid, row, col):  # pixel centre in grid CRS
    t = grid.transform
    return t.c + (col + 0.5) * t.a, t.f + (row + 0.5) * t.e


def read(p):
    with rasterio.open(p) as ds:
        return ds.read(1), type("M", (), {"dtypes": ds.dtypes, "tags": staticmethod(lambda t=ds.tags(): t), "crs": ds.crs})


def test_point_oracle_utm(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 11, 11, 30.0)
    x, y = px(grid, 5, 5)
    f = gj(tmp_path / "p.geojson", [{"type": "Point", "coordinates": [x, y]}], "urn:ogc:def:crs:EPSG::32650")
    r = process_distance("river", [f], aoi, grid, tmp_path)
    d, ds = read(r.path)
    assert d[5, 5] == 0 and d[5, 6] == pytest.approx(30) and d[5, 7] == pytest.approx(60)
    assert d[8, 9] == pytest.approx(np.hypot(3, 4) * 30, rel=1e-6)
    assert ds.dtypes[0] == "float32" and ds.tags()["units"] == "metre" and ds.crs.to_string() == "EPSG:32650"
    assert r.layer_kind == LayerKind.DISTANCE_RIVER and r.status == LayerStatus.PROCESSED
    assert r.stats["min_m"] == 0 and r.stats["n_features"] == 1 and r.stats["crs"] == "EPSG:32650"
    json.dumps(r.stats)


def test_straight_line_and_feature_outside_aoi(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 10, 10, 30.0)
    left, top = grid.transform.c, grid.transform.f
    inside = gj(tmp_path / "in.geojson", [{"type": "LineString", "coordinates": [[left + 150, top + 1000], [left + 150, top - 2000]]}], "EPSG:32650")
    d, _ = read(process_distance("fault", [inside], aoi, grid, tmp_path).path)
    assert np.allclose(d[:, 4], 15) and np.allclose(d[:, 5], 15) and np.allclose(d[:, 0], 135) and np.allclose(d[:, 9], 135)
    # line 100 m beyond the grid's east edge (outside the AOI) must still be found
    right = left + 300
    out = gj(tmp_path / "out.geojson", [{"type": "LineString", "coordinates": [[right + 100, top], [right + 100, top - 300]]}], "EPSG:32650")
    d2, _ = read(process_distance("road", [out], aoi, grid, tmp_path).path)
    assert d2[3, 9] == pytest.approx(115) and d2[3, 0] == pytest.approx(385)


def test_line_in_epsg4326_matches_geodesic(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 20, 20, 30.0)
    lon0 = aoi.bounds[0] - 0.0005  # meridian just west of the grid
    f = gj(tmp_path / "m.geojson", [{"type": "LineString", "coordinates": [[lon0, LAT - 1], [lon0, LAT + 1]]}])  # default EPSG:4326
    d, _ = read(process_distance("river", [f], aoi, grid, tmp_path).path)
    inv = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True)
    geod = Geod(ellps="WGS84")
    for row, col in ((3, 0), (10, 7), (17, 19)):
        lo, la = inv.transform(*px(grid, row, col))
        _, _, dist = geod.inv(lo, la, lon0, la)  # along the parallel ~ perpendicular for a meridian this close
        assert d[row, col] == pytest.approx(dist, rel=3e-3)


def test_mixed_crs_declarations(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 11, 11, 30.0)
    x, y = px(grid, 2, 2)
    lo, la = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True).transform(*px(grid, 8, 8))
    a = gj(tmp_path / "a.geojson", [{"type": "Point", "coordinates": [x, y]}], "urn:ogc:def:crs:EPSG::32650")
    b = gj(tmp_path / "b.geojson", [{"type": "Point", "coordinates": [lo, la]}])
    r = process_distance("road", [a, b], aoi, grid, tmp_path)
    d, _ = read(r.path)
    assert d[2, 2] == pytest.approx(0, abs=1e-3) and d[8, 8] == pytest.approx(0, abs=1e-3) and r.stats["n_features"] == 2
    assert d[5, 5] == pytest.approx(np.hypot(3, 3) * 30, rel=1e-6)


@pytest.mark.parametrize("lon,lat,epsg", [(117.0, 5.9, "EPSG:32650"), (103.8, 1.35, "EPSG:32648"), (-70.0, -33.0, "EPSG:32719")])
def test_different_utm_zones_give_metres(tmp_path, lon, lat, epsg):
    grid, aoi = synthetic_grid(lon, lat, 9, 9, 30.0)
    assert grid.crs == epsg
    lo, la = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True).transform(*px(grid, 4, 4))
    f = gj(tmp_path / "pt.geojson", [{"type": "Point", "coordinates": [lo, la]}])
    d, _ = read(process_distance("river", [f], aoi, grid, tmp_path).path)
    assert d[4, 4] == pytest.approx(0, abs=1e-3) and d[4, 5] == pytest.approx(30, abs=1e-3) and d[4, 6] == pytest.approx(60, abs=1e-3)
    assert d.max() < 200  # metres, not degrees


def test_synthetic_origin_and_hash_stable(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 12, 12, 30.0)
    f = make_vector_geojson(tmp_path, "river", aoi.bounds)
    r1 = process_distance("river", [f], aoi, grid, tmp_path / "o1")
    r2 = process_distance("river", [f], aoi, grid, tmp_path / "o2")
    assert r1.provenance.origin == DataOrigin.SYNTHETIC_FIXTURE and r1.input_hash == r2.input_hash
    assert r1.provenance.source_files == ["synthetic_river.geojson"] and r1.provenance.units == "metre"
    assert rasterio.open(r1.path).tags()["PRECURSOR_SYNTHETIC_FIXTURE"] == "1"
    json.dumps(r1.stats)
    json.dumps(r1.quality.to_dict())


def test_invalid_and_empty_geometries_counted(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 6, 6, 30.0)
    x, y = px(grid, 1, 1)
    bow = {"type": "Polygon", "coordinates": [[[x, y], [x + 50, y + 50], [x + 50, y], [x, y + 50], [x, y]]]}  # self-intersecting
    f = gj(tmp_path / "g.geojson", [{"type": "Point", "coordinates": [x, y]}, bow, {"type": "LineString", "coordinates": []},
                                    {"type": "GeometryCollection", "geometries": []}], "EPSG:32650")
    r = process_distance("fault", [f], aoi, grid, tmp_path)
    assert r.stats["n_features"] == 1 and r.stats["n_skipped"] == 3
    assert r.status == LayerStatus.PARTIALLY_PROCESSED and any("skipped" in w for w in r.warnings)


def test_not_available_cases(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 6, 6, 30.0)
    with pytest.raises(NotAvailable):
        process_distance("river", [], aoi, grid, tmp_path)
    f = gj(tmp_path / "e.geojson", [{"type": "LineString", "coordinates": []}], "EPSG:32650")
    with pytest.raises(NotAvailable):
        process_distance("river", [f], aoi, grid, tmp_path)
    assert not list(tmp_path.glob("distance_*.tif"))


def test_guards(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 6, 6, 30.0)
    f = make_vector_geojson(tmp_path, "road", aoi.bounds)
    geo = TargetGrid("EPSG:4326", Affine(0.001, 0, 117, 0, -0.001, 6), 6, 6)
    with pytest.raises(EnvError, match="geographic"):
        process_distance("road", [f], aoi, geo, tmp_path)
    with pytest.raises(EnvError, match="max_cells"):
        process_distance("road", [f], aoi, grid, tmp_path, max_cells=10)
    with pytest.raises(EnvError, match="unknown distance kind"):
        process_distance("lake", [f], aoi, grid, tmp_path)
    shp = tmp_path / "x.shp"
    shp.write_bytes(b"x")
    with pytest.raises(EnvError, match="GeoJSON"):
        process_distance("road", [shp], aoi, grid, tmp_path)


def test_distance_features_shape(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 12, 12, 30.0)
    rs = [process_distance(k, [make_vector_geojson(tmp_path, k, aoi.bounds)], aoi, grid, tmp_path / k) for k in ("river", "road")]
    out = distance_features(rs)
    assert set(out) == {"features", "warnings"}
    assert out["features"]["distance_river_min_m"]["unit"] == "metre" and "distance_road_mean_m" in out["features"]
    assert not any(w in k for k in out["features"] for w in ("score", "risk", "threshold", "weight", "susceptib"))
    json.dumps(out)
