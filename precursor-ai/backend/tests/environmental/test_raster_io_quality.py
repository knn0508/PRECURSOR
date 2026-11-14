"""inspect_raster / quality tests. ALL fixtures are SYNTHETIC and tagged PRECURSOR_SYNTHETIC_FIXTURE=1; the .hgt/.zip are
imitations of the SRTM/NASADEM layout, NOT real NASADEM tiles. Passing is not real-data validation."""
import numpy as np
import pytest
import rasterio
from affine import Affine

from app.services.environmental import synthetic_raster as syn
from app.services.environmental.raster.io import inspect_raster, read_float, write_geotiff
from app.services.environmental.raster.quality import validate_raster
from app.services.environmental.types import SYNTHETIC_TAG, EnvError


def test_inspect_tif(tmp_path):
    m = inspect_raster(syn.make_plane(tmp_path / "p.tif", shape=(20, 30)))
    assert (m.width, m.height, m.count) == (30, 20, 1)
    assert m.crs == "EPSG:32650" and m.units == "metre" and m.is_synthetic and m.source_kind == "tif"
    assert m.res_x == 30.0 and m.res_y == 30.0 and m.dtype == "float32" and np.isnan(m.nodata)
    assert m.tags[SYNTHETIC_TAG] == "1"


def test_inspect_zip_hgt_nasadem_like(tmp_path):
    m = inspect_raster(syn.make_hgt_zip(tmp_path / "NASADEM_HGT_n06e116.zip"))
    assert (m.width, m.height) == (3601, 3601) and m.dtype == "int16"
    assert m.crs and "4326" in m.crs and m.source_kind == "zip-hgt"
    assert m.nodata == -32768.0
    assert abs(m.res_x - 1 / 3600) < 1e-6 or abs(m.res_x - 1 / 3601) < 1e-6  # as reported by GDAL's HGT driver
    z, _ = read_float(tmp_path / "NASADEM_HGT_n06e116.zip")
    assert np.isnan(z[10:20, 10:20]).all() and np.isfinite(z[0, 0]) and z[0, 0] == 100.0  # void -> NaN, data kept


def test_inspect_bare_hgt(tmp_path):
    m = inspect_raster(syn.make_hgt(tmp_path / "n06e116.hgt"))
    assert (m.width, m.height) == (1201, 1201) and m.source_kind == "hgt" and m.crs


def test_bad_inputs(tmp_path):
    with pytest.raises(FileNotFoundError):
        inspect_raster(tmp_path / "nope.tif")
    (tmp_path / "x.txt").write_text("x")
    with pytest.raises(EnvError):
        inspect_raster(tmp_path / "x.txt")
    import zipfile
    with zipfile.ZipFile(tmp_path / "e.zip", "w") as zf:
        zf.writestr("readme.txt", "x")
    with pytest.raises(EnvError):
        inspect_raster(tmp_path / "e.zip")


def _no_crs_tif(path):
    with rasterio.open(path, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32",
                       transform=Affine(1, 0, 0, 0, -1, 4), nodata=np.nan) as ds:
        ds.write(np.ones((4, 4), dtype="float32"), 1)
    return path


def test_missing_crs_reported_not_guessed(tmp_path):
    p = _no_crs_tif(tmp_path / "nocrs.tif")
    m = inspect_raster(p)
    assert m.crs is None and m.crs_error
    q = validate_raster(p)
    assert any(c.startswith("crs_missing") for c in q.checks_failed) and q.crs is None


def test_quality_counts_nan_not_zero(tmp_path):
    q = validate_raster(syn.make_noisy_terrain(tmp_path / "n.tif", shape=(64, 64), hole=(0, 10, 0, 10)))
    assert q.total_pixels == 4096 and q.valid_pixels == 4096 - 100
    assert q.missing_percent == pytest.approx(100 * 100 / 4096, abs=1e-3)
    assert q.valid_percent + q.missing_percent == pytest.approx(100.0)
    assert not q.checks_failed and q.native_resolution["unit"] == "crs_linear_unit"


def test_quality_flags_inf_and_all_nodata(tmp_path):
    t = Affine(1, 0, 0, 0, -1, 4)
    p = write_geotiff(tmp_path / "inf.tif", np.array([[np.inf, 1], [2, 3]], dtype="float32"), t, "EPSG:32650")
    assert any("values_finite" in c for c in validate_raster(p).checks_failed)
    p2 = write_geotiff(tmp_path / "nan.tif", np.full((3, 3), np.nan, dtype="float32"), t, "EPSG:32650")
    q = validate_raster(p2)
    assert q.valid_pixels == 0 and q.valid_percent == 0.0 and any("has_valid_pixels" in c for c in q.checks_failed)


def test_integer_raster_without_nodata_warns(tmp_path):
    p = tmp_path / "i.tif"
    with rasterio.open(p, "w", driver="GTiff", height=3, width=3, count=1, dtype="int16", crs="EPSG:32650",
                       transform=Affine(1, 0, 0, 0, -1, 3)) as ds:
        ds.write(np.zeros((3, 3), dtype="int16"), 1)
    assert any("no nodata" in w for w in validate_raster(p).warnings)
