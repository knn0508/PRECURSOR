"""User-provided lithology -> class raster on a metric grid. SYNTHETIC inputs only."""
import app.core.geo_env  # noqa: F401

import json

import numpy as np
import pytest
import rasterio
from affine import Affine
from shapely.geometry import Polygon

from app.services.environmental.external_inputs import discover_external
from app.services.environmental.external_synthetic import (
    make_lithology_geojson, make_lithology_raster, synthetic_grid, write_tif,
)
from app.services.environmental.features.lithology_features import lithology_features
from app.services.environmental.lithology.lithology_processor import process_lithology
from app.services.environmental.raster.alignment import TargetGrid
from app.services.environmental.types import DataOrigin, EnvError, LayerStatus, NotAvailable

LON, LAT = 117.0, 5.9


def bounds_of(grid):
    t = grid.transform
    return t.c, t.f + t.e * grid.height, t.c + t.a * grid.width, t.f


def read(p):
    with rasterio.open(p) as ds:
        return ds.read(1), ds.dtypes[0], ds.nodata, ds.tags()


def test_raster_happy_path_oracle(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 30, 30, 30.0)
    f = make_lithology_raster(tmp_path / "in", bounds_of(grid), grid.crs)
    r = process_lithology([f], aoi, grid, tmp_path / "out")
    arr, dt, nd, tags = read(r.path)
    assert dt == "uint16" and nd == 65535 and set(np.unique(arr)) == {10, 20, 30}
    assert tags["PRECURSOR_SYNTHETIC_FIXTURE"] == "1" and tags["units"] == "class id"
    assert [(c["class_id"], c["name"]) for c in r.classes] == [(10, "synthetic unit A"), (20, "synthetic unit B"), (30, "synthetic unit C")]
    assert all(c["percent"] == pytest.approx(100 / 3, abs=1e-4) for c in r.classes)
    assert r.status == LayerStatus.PROCESSED and r.quality.valid_percent == 100.0 and not r.unknown_classes
    assert r.provenance.origin == DataOrigin.SYNTHETIC_FIXTURE
    assert r.provenance.source_files == ["synthetic_lithology.tif", "synthetic_lithology.legend.json"]
    assert r.legend["source"].startswith("SYNTHETIC")
    json.dumps(r.stats), json.dumps(r.legend), json.dumps(r.quality.to_dict())


def test_legend_missing_keeps_ids_names_unknown(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 30, 30, 30.0)
    f = make_lithology_raster(tmp_path / "in", bounds_of(grid), grid.crs, with_legend=False)
    r = process_lithology([f], aoi, grid, tmp_path / "out")
    assert [c["class_id"] for c in r.classes] == [10, 20, 30]
    assert all(c["name"] == f"class {c['class_id']}" for c in r.classes)  # nothing invented
    assert any("names unknown" in w for w in r.warnings) and r.legend["legend_present"] is False


def test_ids_missing_from_legend_reported_unknown(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 30, 30, 30.0)
    f = make_lithology_raster(tmp_path / "in", bounds_of(grid), grid.crs)
    (tmp_path / "in" / "synthetic_lithology.legend.json").write_text(json.dumps({"classes": [{"id": 10, "name": "u10"}]}), encoding="utf-8")
    r = process_lithology([f], aoi, grid, tmp_path / "out")
    assert [u["class_id"] for u in r.unknown_classes] == [20, 30] and r.status == LayerStatus.PARTIALLY_PROCESSED
    assert [c["class_id"] for c in r.classes] == [10]


def test_invalid_legend_rejected(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 30, 30, 30.0)
    f = make_lithology_raster(tmp_path / "in", bounds_of(grid), grid.crs)
    (tmp_path / "in" / "synthetic_lithology.legend.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(EnvError, match="legend"):
        process_lithology([f], aoi, grid, tmp_path / "out")


@pytest.mark.parametrize("res,n", [(6.0, 150), (90.0, 10)])
def test_nearest_preserves_ids_finer_and_coarser(tmp_path, res, n):
    base, _ = synthetic_grid(LON, LAT, 30, 30, 30.0)
    f = make_lithology_raster(tmp_path / "in", bounds_of(base), base.crs)
    grid, aoi = synthetic_grid(LON, LAT, n, n, res)
    arr, *_ = read(process_lithology([f], aoi, grid, tmp_path / "out").path)
    assert set(np.unique(arr)) <= {10, 20, 30, 65535}


def test_source_raster_in_different_crs(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 30, 30, 30.0)
    w, s, e, n = aoi.bounds
    pad = 0.001
    f = make_lithology_raster(tmp_path / "in", (w - pad, s - pad, e + pad, n + pad), "EPSG:4326")
    r = process_lithology([f], aoi, grid, tmp_path / "out")
    arr, *_ = read(r.path)
    assert set(np.unique(arr[arr != 65535])) == {10, 20, 30} and r.quality.valid_percent == 100.0
    assert r.quality.native_resolution["unit"] == "degree" and r.quality.processing_resolution["unit"] == "metre"


def test_vector_polygons_with_legend(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 40, 40, 30.0)
    f = make_lithology_geojson(tmp_path / "in", aoi.bounds)
    r = process_lithology([f], aoi, grid, tmp_path / "out")
    got = {c["class_id"]: (c["name"], c["percent"]) for c in r.classes}
    assert set(got) == {1, 2} and got[1][0] == "synthetic unit A"
    assert got[1][1] + got[2][1] == pytest.approx(100.0) and got[1][1] == pytest.approx(50, abs=3)
    assert r.provenance.origin == DataOrigin.SYNTHETIC_FIXTURE


def test_vector_without_legend_needs_attribute_then_stable_ids(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 40, 40, 30.0)
    f = make_lithology_geojson(tmp_path / "in", aoi.bounds)
    (tmp_path / "in" / "synthetic_geology.legend.json").unlink()
    with pytest.raises(EnvError, match="attribute"):
        process_lithology([f], aoi, grid, tmp_path / "o1")
    r = process_lithology([f], aoi, grid, tmp_path / "o2", attribute="unit")
    assert [(c["class_id"], c["name"]) for c in r.classes] == [(1, "synthetic unit A"), (2, "synthetic unit B")]  # sorted values
    assert any(c["name"] == "synthetic unit B" and c["id"] == 2 for c in r.legend["classes"])  # mapping recorded
    assert any("no <stem>.legend.json" in w for w in r.warnings)


def test_not_available_and_all_nodata(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 10, 10, 30.0)
    with pytest.raises(NotAvailable):
        process_lithology([], aoi, grid, tmp_path)
    f = write_tif(tmp_path / "nd.tif", np.full((10, 10), 65535), bounds_of(grid), grid.crs, "uint16", 65535, {})
    with pytest.raises(NotAvailable, match="valid 0%"):
        process_lithology([f], aoi, grid, tmp_path / "out")
    assert not (tmp_path / "out" / "lithology.tif").exists()
    far = write_tif(tmp_path / "far.tif", np.full((5, 5), 3), (0, 0, 500, 500), grid.crs, "uint16", 65535, {})
    with pytest.raises(NotAvailable):
        process_lithology([far], aoi, grid, tmp_path / "out")


def test_non_integer_rejected_and_geographic_grid_rejected(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 10, 10, 30.0)
    f = write_tif(tmp_path / "f.tif", np.full((10, 10), 1.5), bounds_of(grid), grid.crs, "float32", -1.0, {})
    with pytest.raises(EnvError, match="integer"):
        process_lithology([f], aoi, grid, tmp_path)
    geo = TargetGrid("EPSG:4326", Affine(0.001, 0, 117, 0, -0.001, 6), 10, 10)
    with pytest.raises(EnvError, match="geographic"):
        process_lithology([f], aoi, geo, tmp_path)


def test_aoi_smaller_than_source_cell(tmp_path):
    grid, big = synthetic_grid(LON, LAT, 30, 30, 30.0)
    f = make_lithology_raster(tmp_path / "in", bounds_of(grid), grid.crs)
    c = big.centroid
    tiny = Polygon([(c.x, c.y), (c.x + 1e-7, c.y), (c.x + 1e-7, c.y + 1e-7), (c.x, c.y + 1e-7)])
    r = process_lithology([f], tiny, grid, tmp_path / "out")
    assert r.quality.total_pixels >= 1 and r.quality.valid_percent == 100.0 and any("smaller than one grid pixel" in w for w in r.warnings)


def test_features_and_discovery(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 30, 30, 30.0)
    root = tmp_path / "data"
    assert discover_external(root, "lithology", aoi, (".tif", ".json")) == []  # missing dir
    d = root / "external" / "lithology"
    f = make_lithology_raster(d, bounds_of(grid), grid.crs)
    far = write_tif(d / "far.tif", np.full((5, 5), 3), (0, 0, 500, 500), grid.crs, "uint16", 65535, {})
    found = discover_external(root, "lithology", aoi, (".tif", ".json"))
    assert found == [f] and far not in found  # legend sidecar and non-covering file excluded
    out = lithology_features(process_lithology(found, aoi, grid, tmp_path / "out"))
    assert set(out) == {"features", "warnings"} and out["features"]["lithology_class_10_percent"]["unit"].startswith("percent")
    assert not any(w in k for k in out["features"] for w in ("score", "risk", "threshold", "weight", "susceptib", "hardness", "erod"))
