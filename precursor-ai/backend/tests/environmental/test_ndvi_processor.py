"""User-provided NDVI -> float32 on a metric grid. SYNTHETIC inputs only."""
import app.core.geo_env  # noqa: F401

import json

import numpy as np
import pytest
import rasterio
from affine import Affine
from shapely.geometry import Polygon

from app.services.environmental.external_synthetic import make_ndvi_raster, synthetic_grid, write_tif
from app.services.environmental.features.vegetation_features import vegetation_features
from app.services.environmental.raster.alignment import TargetGrid
from app.services.environmental.types import DataOrigin, EnvError, LayerStatus, NotAvailable
from app.services.environmental.vegetation.ndvi_processor import process_ndvi

LON, LAT = 117.0, 5.9


def bounds_of(grid):
    t = grid.transform
    return t.c, t.f + t.e * grid.height, t.c + t.a * grid.width, t.f


def read(p):
    with rasterio.open(p) as ds:
        return ds.read(1), ds.dtypes[0], ds.tags()


def test_generic_happy_path(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 30, 30, 30.0)
    f = make_ndvi_raster(tmp_path / "in", bounds_of(grid), grid.crs)
    r = process_ndvi([f], aoi, grid, tmp_path / "out")
    arr, dt, tags = read(r.path)
    assert dt == "float32" and tags["PRECURSOR_SYNTHETIC_FIXTURE"] == "1"
    assert r.stats["mean"] == pytest.approx(0.3, abs=1e-4) and r.stats["min"] == pytest.approx(-0.2, abs=1e-5)
    assert r.stats["max"] == pytest.approx(0.8, abs=1e-5) and r.stats["std"] == pytest.approx(np.std(np.linspace(-0.2, 0.8, 30)), abs=1e-4)
    assert r.status == LayerStatus.PROCESSED and r.stats["valid_percent"] == 100.0
    assert r.observation == {"synthetic_ndvi.tif": "UNKNOWN"}  # never invented
    assert r.provenance.origin == DataOrigin.SYNTHETIC_FIXTURE and r.provenance.units.startswith("NDVI")
    json.dumps(r.stats), json.dumps(r.quality.to_dict())


def test_modis_scaling_only_when_declared(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 30, 30, 30.0)
    f = make_ndvi_raster(tmp_path / "in", bounds_of(grid), grid.crs, modis=True)
    r = process_ndvi([f], aoi, grid, tmp_path / "out")
    arr, *_ = read(r.path)
    assert np.isnan(arr[0, 0]) and np.isfinite(arr).sum() == 899  # fill value -3000 masked, not zero
    assert r.stats["max"] == pytest.approx(0.8, abs=1e-4) and r.stats["per_file"][f.name]["scale_applied"] == 0.0001
    assert r.stats["per_file"][f.name]["n_fill"] == 1 and r.status == LayerStatus.PARTIALLY_PROCESSED
    assert r.observation[f.name].startswith("2020-01-01")  # MODIS A2020001 day-of-year parsed from the file name


def test_no_declared_scale_means_dn_are_not_scaled(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 10, 10, 30.0)
    dn = np.full((10, 10), 5000)
    dn[0, :3] = (0, 1, -1)
    f = write_tif(tmp_path / "dn.tif", dn, bounds_of(grid), grid.crs, "int16", -3000, {})
    r = process_ndvi([f], aoi, grid, tmp_path / "o1")
    assert r.stats["n_out_of_range"] == 97 and r.stats["max"] == 1.0 and r.stats["n_valid_pixels"] == 3
    r2 = process_ndvi([f], aoi, grid, tmp_path / "o2", scale_factor=0.0001)  # explicit option
    assert r2.stats["n_out_of_range"] == 0 and r2.stats["max"] == pytest.approx(0.5)


def test_out_of_range_counted_not_clipped(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 10, 10, 30.0)
    a = np.full((10, 10), 0.4, dtype="float32")
    a[0, 0], a[1, 1] = 1.5, -2.0
    f = write_tif(tmp_path / "v.tif", a, bounds_of(grid), grid.crs, "float32", -9999.0, {})
    r = process_ndvi([f], aoi, grid, tmp_path / "out")
    arr, *_ = read(r.path)
    assert r.stats["n_out_of_range"] == 2 and np.isnan(arr[0, 0]) and np.isnan(arr[1, 1])
    assert not np.any(arr == 1.0) and not np.any(arr == -1.0)  # never clipped
    assert r.status == LayerStatus.PARTIALLY_PROCESSED and any("outside [-1, 1]" in w for w in r.warnings)
    assert r.stats["min"] == pytest.approx(0.4) and r.stats["max"] == pytest.approx(0.4)


def test_mod13_name_without_scale_warns(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 10, 10, 30.0)
    a = np.full((10, 10), 0.2, dtype="float32")
    f = write_tif(tmp_path / "MOD13Q1.A2021065.tif", a, bounds_of(grid), grid.crs, "float32", -9999.0, {})
    r = process_ndvi([f], aoi, grid, tmp_path / "out")
    assert any("no scale_factor" in w for w in r.warnings)


def test_not_available_and_all_nodata(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 10, 10, 30.0)
    with pytest.raises(NotAvailable):
        process_ndvi([], aoi, grid, tmp_path)
    f = write_tif(tmp_path / "nd.tif", np.full((10, 10), -9999.0), bounds_of(grid), grid.crs, "float32", -9999.0, {})
    with pytest.raises(NotAvailable, match="valid 0%"):
        process_ndvi([f], aoi, grid, tmp_path / "out")
    assert not (tmp_path / "out" / "ndvi.tif").exists()
    nan = write_tif(tmp_path / "nan.tif", np.full((10, 10), np.nan), bounds_of(grid), grid.crs, "float32", np.nan, {})
    with pytest.raises(NotAvailable):
        process_ndvi([nan], aoi, grid, tmp_path / "out")


def test_source_in_other_crs_bilinear(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 20, 20, 30.0)
    w, s, e, n = aoi.bounds
    pad = 0.001
    f = write_tif(tmp_path / "g.tif", np.full((12, 12), 0.4), (w - pad, s - pad, e + pad, n + pad), "EPSG:4326", "float32", -9999.0, {})
    r = process_ndvi([f], aoi, grid, tmp_path / "out")
    assert r.stats["mean"] == pytest.approx(0.4, abs=1e-5) and r.stats["valid_percent"] == 100.0
    assert r.quality.native_resolution["unit"] == "degree" and r.quality.processing_resolution["unit"] == "metre"


def test_aoi_smaller_than_source_cell(tmp_path):
    grid, big = synthetic_grid(LON, LAT, 20, 20, 30.0)
    f = write_tif(tmp_path / "c.tif", np.full((2, 2), 0.25), (grid.transform.c - 500, grid.transform.f - 1500, grid.transform.c + 1100, grid.transform.f + 100)
                  , grid.crs, "float32", -9999.0, {})
    c = big.centroid
    tiny = Polygon([(c.x, c.y), (c.x + 1e-7, c.y), (c.x + 1e-7, c.y + 1e-7), (c.x, c.y + 1e-7)])
    r = process_ndvi([f], tiny, grid, tmp_path / "out")
    assert r.stats["mean"] == pytest.approx(0.25) and any("smaller than one grid pixel" in w for w in r.warnings)


def test_geographic_grid_rejected(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 10, 10, 30.0)
    f = make_ndvi_raster(tmp_path / "in", bounds_of(grid), grid.crs, shape=(10, 10))
    geo = TargetGrid("EPSG:4326", Affine(0.001, 0, 117, 0, -0.001, 6), 10, 10)
    with pytest.raises(EnvError, match="geographic"):
        process_ndvi([f], aoi, geo, tmp_path)


def test_features_descriptive_only(tmp_path):
    grid, aoi = synthetic_grid(LON, LAT, 30, 30, 30.0)
    f = make_ndvi_raster(tmp_path / "in", bounds_of(grid), grid.crs)
    r = process_ndvi([f], aoi, grid, tmp_path / "out")
    out = vegetation_features(r)
    assert set(out) == {"features", "warnings"} and out["features"]["ndvi_mean"]["value"] == pytest.approx(0.3, abs=1e-4)
    assert not any(w in k for k in out["features"] for w in ("score", "risk", "threshold", "weight", "health", "drought", "susceptib"))
    json.dumps(out)
    assert r.input_hash == process_ndvi([f], aoi, grid, tmp_path / "out2").input_hash
