"""TEST FIXTURE, synthetic, not a NASA acquisition: every file here is generated in tmp_path."""
import zipfile
from datetime import UTC, datetime

import h5py
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from app.services.data_acquisition.types import GranuleRecord, Maturity, ProviderName
from app.services.data_acquisition.validation_service import FileValidationService

@pytest.fixture(autouse=True)
def _own_proj_db(monkeypatch):
    # A system PostgreSQL/PostGIS PROJ_LIB (older proj.db) can shadow the wheel's data; prefer pyproj's.
    import pyproj

    monkeypatch.setenv("PROJ_DATA", pyproj.datadir.get_data_dir())
    monkeypatch.setenv("PROJ_LIB", pyproj.datadir.get_data_dir())


T0 = datetime(2025, 11, 1, 1, 2, 3, tzinfo=UTC)


def granule(**kw):
    d = dict(
        provider=ProviderName.NISAR, granule_id="G1", collection_short_name="NISAR_L2_GUNW_V1",
        product_type="GUNW", version="1", maturity=Maturity.VALIDATED,
        acquisition_start=T0, acquisition_end=T0, footprint=box(100, 4, 101, 5),
    )
    d.update(kw)
    return GranuleRecord(**d)


def nisar_h5(path, product_type="GUNW", start="2025-11-01T01:02:03.000000"):
    with h5py.File(path, "w") as f:
        g = f.create_group("science/LSAR/identification")
        g["productType"] = product_type
        g["granuleId"] = "G1"
        g["boundingPolygon"] = "POLYGON ((100 4, 101 4, 101 5, 100 5, 100 4))"
        g["zeroDopplerStartTime"] = start
        g["zeroDopplerEndTime"] = start


def check(rep, name):
    return next(c for c in rep.checks if c.name == name)


svc = FileValidationService()


def test_nisar_h5_ok(tmp_path):
    p = tmp_path / "a.h5"
    nisar_h5(p)
    rep = svc.validate(p, granule())
    assert rep.ok, rep.checks
    assert rep.extracted["productType"] == "GUNW"
    assert "POLYGON" in rep.extracted["bounding_polygon_wkt"]
    assert len(rep.sha256) == 64


def test_wrong_product_type_fails(tmp_path):
    p = tmp_path / "a.h5"
    nisar_h5(p, product_type="GCOV")
    rep = svc.validate(p, granule())
    assert not rep.ok and not check(rep, "product_type_matches").passed


def test_h5_missing_identification_keys_tolerated(tmp_path):
    p = tmp_path / "a.h5"
    with h5py.File(p, "w") as f:
        f.create_group("science/LSAR/identification")["granuleId"] = "G1"
    assert svc.validate(p, granule()).ok


def test_h5_without_identification_group_fails(tmp_path):
    p = tmp_path / "a.h5"
    with h5py.File(p, "w") as f:
        f.create_group("science/LSAR/GUNW")
    assert not check(svc.validate(p, granule()), "format_opens").passed


def test_file_date_far_from_granule_fails(tmp_path):
    p = tmp_path / "a.h5"
    nisar_h5(p, start="2024-01-01T00:00:00")
    assert not check(svc.validate(p, granule()), "dates_valid").passed


def test_corrupt_h5_does_not_raise(tmp_path):
    p = tmp_path / "a.h5"
    p.write_bytes(b"not hdf5 at all" * 10)
    rep = svc.validate(p, granule())
    assert not rep.ok and not check(rep, "format_opens").passed


def test_empty_and_missing(tmp_path):
    p = tmp_path / "e.h5"
    p.write_bytes(b"")
    rep = svc.validate(p, granule())
    assert not rep.ok and not check(rep, "size_gt_zero").passed
    rep = svc.validate(tmp_path / "nope.h5", granule())
    assert not rep.ok and not check(rep, "file_exists").passed


def test_checksum(tmp_path):
    import hashlib

    p = tmp_path / "a.h5"
    nisar_h5(p)
    md5 = hashlib.md5(p.read_bytes()).hexdigest().upper()
    assert svc.validate(p, granule(), expected_checksum=md5, expected_checksum_algorithm="MD5").ok
    rep = svc.validate(p, granule(), expected_checksum="0" * 32, expected_checksum_algorithm="MD5")
    assert not check(rep, "checksum").passed


def test_geotiff(tmp_path):
    p = tmp_path / "a.tif"
    with rasterio.open(p, "w", driver="GTiff", width=4, height=3, count=1, dtype="int16",
                       crs="EPSG:4326", transform=from_origin(100, 5, 0.1, 0.1)) as ds:
        ds.write(np.zeros((1, 3, 4), dtype="int16"))
    g = granule(provider=ProviderName.NASADEM, product_type="DEM", maturity=None)
    rep = svc.validate(p, g)
    assert rep.ok, rep.checks
    assert rep.extracted["width"] == 4


def test_geotiff_without_crs_fails(tmp_path):
    p = tmp_path / "a.tif"
    with rasterio.open(p, "w", driver="GTiff", width=2, height=2, count=1, dtype="int16") as ds:
        ds.write(np.zeros((1, 2, 2), dtype="int16"))
    g = granule(provider=ProviderName.NASADEM, product_type="DEM", maturity=None)
    assert not check(svc.validate(p, g), "format_opens").passed


def test_hgt_sizes(tmp_path):
    g = granule(provider=ProviderName.NASADEM, product_type="DEM", maturity=None)
    good, bad = tmp_path / "N04E100.hgt", tmp_path / "N05E100.hgt"
    good.write_bytes(b"\0" * (1201 * 1201 * 2))
    bad.write_bytes(b"\0" * 1000)
    assert svc.validate(good, g).ok
    assert not check(svc.validate(bad, g), "format_opens").passed


def test_zip(tmp_path):
    g = granule(provider=ProviderName.NASADEM, product_type="DEM", maturity=None)
    ok, bad, empty = (tmp_path / n for n in ("ok.zip", "bad.zip", "empty.zip"))
    with zipfile.ZipFile(ok, "w") as z:
        z.writestr("N04E100.hgt", b"\0" * (1201 * 1201 * 2))
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("N04E100.hgt", b"\0" * 10)
    with zipfile.ZipFile(empty, "w"):
        pass
    assert svc.validate(ok, g).ok
    assert not svc.validate(bad, g).ok
    assert not svc.validate(empty, g).ok


def test_csv_and_unknown_extension(tmp_path):
    g = granule(provider=ProviderName.LANDSLIDE_CATALOG, product_type="CATALOG", maturity=None)
    c = tmp_path / "a.csv"
    c.write_text("id,lat,lon\n1,2,3\n")
    assert svc.validate(c, g).ok
    u = tmp_path / "a.xyz"
    u.write_bytes(b"abc")
    rep = svc.validate(u, g)
    assert not rep.ok and "unsupported" in check(rep, "format_opens").detail


def test_metadata_checks(tmp_path):
    p = tmp_path / "a.h5"
    nisar_h5(p)
    bad_fp = granule(footprint=box(100, 4, 200, 5))
    assert not check(svc.validate(p, bad_fp), "footprint_valid").passed
    assert not check(svc.validate(p, granule(version="")), "version_and_maturity_recorded").passed
    assert not check(svc.validate(p, granule(maturity=None)), "version_and_maturity_recorded").passed
    assert not check(svc.validate(p, granule(acquisition_start=datetime(1960, 1, 1, tzinfo=UTC))), "dates_valid").passed
    assert not check(svc.validate(p, granule(acquisition_end=datetime(2999, 1, 1, tzinfo=UTC))), "dates_valid").passed
    assert not check(svc.validate(p, granule(acquisition_end=datetime(2025, 1, 1, tzinfo=UTC))), "dates_valid").passed
