"""Soil processor tests on SYNTHETIC GeoTIFFs (not SoilGrids data)."""
import numpy as np
import pytest
from pyproj import Transformer

from app.services.environmental.features.soil_features import soil_features
from app.services.environmental.providers.soilgrids import convert, parse_soil_filename
from app.services.environmental.providers.synthetic import write_synthetic_soil
from app.services.environmental.soil.soil_processor import process_soil
from app.services.environmental.types import DataOrigin, NotAvailable

BB = (116.0, 5.5, 116.4, 5.9)
IGH = "+proj=igh +lon_0=0 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"


def test_scaling_factor_oracle():
    assert convert("clay", "mean", 253) == pytest.approx(25.3)
    assert convert("phh2o", "mean", 65) == pytest.approx(6.5)
    assert convert("bdod", "mean", 135) == pytest.approx(1.35)
    assert convert("nitrogen", "mean", 250) == pytest.approx(2.5)
    assert parse_soil_filename("clay_5-15cm_Q0.05.tif")["statistic"] == "Q0.05"
    assert parse_soil_filename("random.tif") is None


def test_units_depth_preserved_and_nodata_excluded(tmp_path):
    raw = np.array([[200, 300], [400, -32768]])
    write_synthetic_soil(tmp_path, "clay", 5, 15, "mean", raw, west=116.0, north=5.9, pixel=0.2)
    r = process_soil([tmp_path / "clay_5-15cm_mean.tif"], BB)
    (l,) = r.layers
    assert (l["top_cm"], l["bottom_cm"], l["statistic"]) == (5, 15, "mean")
    assert l["source_units"] == "g/kg" and l["converted_units"] == "g/100g (%)" and l["scale_factor"] == 10
    assert l["raw_stats"]["mean"] == pytest.approx(300.0) and l["converted_stats"]["mean"] == pytest.approx(30.0)
    assert l["valid_pixels"] == 3 and l["total_pixels"] == 4 and l["valid_percent"] == pytest.approx(75.0)
    assert r.provenance.origin == DataOrigin.SYNTHETIC_FIXTURE and r.provenance.source_files == ["clay_5-15cm_mean.tif"]
    f = soil_features(r)["values"][0]
    assert f["units"] == "g/100g (%)" and f["raw_units"] == "g/kg" and f["mean"] == pytest.approx(30.0)


def test_homolosine_raster_is_clipped_in_its_own_crs(tmp_path):
    tr = Transformer.from_crs("EPSG:4326", IGH, always_xy=True)
    l, b, r_, t = tr.transform_bounds(*BB, densify_pts=21)
    pix = 250.0
    west, north = l - 5000, t + 5000
    ny, nx = int((t - b + 10000) / pix) + 2, int((r_ - l + 10000) / pix) + 2
    raw = np.full((ny, nx), 100, dtype="int16")
    raw[10:-10, 10:-10] = 500  # block comfortably larger than the AOI window
    write_synthetic_soil(tmp_path, "soc", 0, 5, "mean", raw, crs=IGH, west=west, north=north, pixel=pix)
    res = process_soil([tmp_path / "soc_0-5cm_mean.tif"], BB)
    assert res.layers[0]["raw_stats"]["min"] == 500.0 and res.layers[0]["raw_stats"]["max"] == 500.0
    assert res.layers[0]["aoi_coverage_percent"] == pytest.approx(100.0)
    # a (wrong) lon/lat assumption would have missed the raster entirely: AOI elsewhere on Earth is NotAvailable
    with pytest.raises(NotAvailable):
        process_soil([tmp_path / "soc_0-5cm_mean.tif"], (10.0, 40.0, 10.4, 40.4))


def test_no_files_or_no_overlap_raises(tmp_path):
    with pytest.raises(NotAvailable):
        process_soil([], BB)
    write_synthetic_soil(tmp_path, "clay", 0, 5, "mean", np.ones((2, 2)), west=10.0, north=10.0, pixel=0.1)
    with pytest.raises(NotAvailable):
        process_soil([tmp_path / "clay_0-5cm_mean.tif"], BB)


def test_soil_map_rasters_converted_values_and_georef(tmp_path):
    import json
    import rasterio
    raw = np.array([[200, 300], [400, -32768]])
    write_synthetic_soil(tmp_path, "clay", 5, 15, "mean", raw, west=116.0, north=5.9, pixel=0.2)
    out = tmp_path / "out"
    r = process_soil([tmp_path / "clay_5-15cm_mean.tif"], BB, out_dir=out)
    (e,) = r.rasters
    json.dumps(e)
    assert (e["property"], e["top_cm"], e["bottom_cm"], e["statistic"], e["units"]) == ("clay", 5, 15, "mean", "g/100g (%)")
    assert e["path"].endswith("soil_clay_5-15cm_mean.tif")
    with rasterio.open(e["path"]) as s:
        a = s.read(1)
        assert s.dtypes[0] == "float32" and s.bounds.left == pytest.approx(116.0) and s.bounds.top == pytest.approx(5.9)
        assert s.tags()["scale_factor"] == "10" and s.tags()["raw_units"] == "g/kg"
    assert a[0, 0] == pytest.approx(20.0) and a[0, 1] == pytest.approx(30.0) and np.isnan(a[1, 1])


def test_soil_out_dir_none_unchanged(tmp_path):
    write_synthetic_soil(tmp_path, "clay", 5, 15, "mean", np.array([[200, 300], [400, 500]]), west=116.0, north=5.9, pixel=0.2)
    r = process_soil([tmp_path / "clay_5-15cm_mean.tif"], BB)
    assert r.rasters == [] and not (tmp_path / "out").exists()
