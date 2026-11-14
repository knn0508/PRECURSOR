"""prepare_dem / compute_terrain / terrain_features tests. ALL fixtures are SYNTHETIC (PRECURSOR_SYNTHETIC_FIXTURE=1),
including the imitation NASADEM .zip; nothing here is real NASADEM data or real-data validation."""
import numpy as np
import pytest
from shapely.geometry import box

from app.services.environmental import synthetic_raster as syn
from app.services.environmental.dem.dem_processor import compute_terrain, prepare_dem
from app.services.environmental.features.terrain_features import terrain_features
from app.services.environmental.raster.io import inspect_raster, read_float, write_geotiff
from app.services.environmental.types import SYNTHETIC_TAG, EnvError, NotAvailable


def test_prepare_dem_mosaic_clip_and_terrain(tmp_path):
    t = syn.make_mosaic_tiles(tmp_path / "tiles")
    aoi = box(116.10, 6.05, 116.30, 6.15)  # spans tile_a, overlap with tile_b, ends in tile_b
    dem = prepare_dem([t["tile_a"], t["tile_b"]], aoi, tmp_path / "out")
    assert dem.elevation_path.name == "elevation.tif" and dem.units == "metre" and dem.is_synthetic
    assert dem.aoi_coverage_percent == pytest.approx(100.0, abs=0.01)
    assert dem.quality.valid_percent == pytest.approx(100.0) and not dem.quality.checks_failed
    ter = compute_terrain(dem.elevation_path, tmp_path / "out")
    sm, am, em = (inspect_raster(p) for p in (ter.slope_path, ter.aspect_path, dem.elevation_path))
    assert (sm.width, sm.height, sm.transform) == (em.width, em.height, em.transform) == (am.width, am.height, am.transform)
    assert sm.units == "degree" and am.tags[SYNTHETIC_TAG] == "1" and "clockwise from north" in am.tags["measurement"]
    s, _ = read_float(ter.slope_path)
    a, _ = read_float(ter.aspect_path)
    # tile_value rises 1000 m/deg east and 500 m/deg north: surface descends west/south -> aspect pointing W-SW (>180)
    assert np.nanmin(a) > 180 and np.nanmax(a) < 270 and np.isnan(s[0]).all()
    assert ter.flat_count == 0


def test_prepare_dem_partial_coverage_and_missing_tile_reported(tmp_path):
    t = syn.make_mosaic_tiles(tmp_path / "tiles")
    dem = prepare_dem([t["tile_a"], t["tile_c"]], box(116.10, 6.05, 116.65, 6.15), tmp_path / "o")
    assert dem.quality.missing_percent > 0 and any("no tile" in w for w in dem.warnings)
    assert np.isnan(read_float(dem.elevation_path)[0]).any()  # gap stays NaN


def test_prepare_dem_not_available(tmp_path):
    t = syn.make_mosaic_tiles(tmp_path / "tiles")
    with pytest.raises(NotAvailable):
        prepare_dem([], box(0, 0, 1, 1), tmp_path / "o")
    with pytest.raises(NotAvailable):
        prepare_dem([t["tile_a"]], box(10, 10, 11, 11), tmp_path / "o")


def test_prepare_dem_from_zip_hgt_assumption_flagged(tmp_path):
    z = syn.make_hgt_zip(tmp_path / "NASADEM_HGT_n06e116.zip", size=3601)
    dem = prepare_dem([z], box(116.2, 6.2, 116.3, 6.3), tmp_path / "o")
    assert dem.units == "metre" and any("ASSUMED" in w for w in dem.warnings)
    assert "NOT verified" in dem.tags["vertical_reference_note"]
    assert dem.aoi_coverage_percent == pytest.approx(100.0, abs=0.1)
    assert dem.quality.native_resolution["unit"] == "degree"


def test_non_metre_units_rejected(tmp_path):
    z, m = read_float(syn.make_plane(tmp_path / "p.tif"))
    from affine import Affine
    f = write_geotiff(tmp_path / "ft.tif", z, Affine(*m.transform), m.crs, {"units": "foot"})
    with pytest.raises(EnvError):
        compute_terrain(f, tmp_path / "o")


def test_terrain_features_descriptive_only(tmp_path):
    dem_p = syn.make_plane(tmp_path / "e.tif", slope_deg=30, downslope_azimuth_deg=90, shape=(30, 30))
    ter = compute_terrain(dem_p, tmp_path / "o")
    f = terrain_features(dem_p, ter.slope_path, ter.aspect_path, None)
    v = f["features"]
    assert v["slope_mean"]["value"] == pytest.approx(30.0, abs=1e-3) and v["slope_max"]["value"] == pytest.approx(30.0, abs=1e-3)
    assert v["elevation_range"]["value"] == pytest.approx(v["elevation_max"]["value"] - v["elevation_min"]["value"])
    assert v["elevation_mean"]["unit"] == "metre" and v["slope_mean"]["unit"] == "degree"
    assert v["aspect_circular_mean"]["value"] == pytest.approx(90.0, abs=1e-3)
    assert v["aspect_resultant_length"]["value"] == pytest.approx(1.0)
    assert v["aspect_sector_counts"]["value"]["E"] == 28 * 28
    assert sum(v["slope_histogram"]["value"]["counts"]) == 28 * 28 and sum(v["slope_histogram"]["value"]["counts"][5:7]) == 784  # 30 deg sits on a bin edge
    assert f["valid_pixel_count"] == 900 and f["flat_pixel_count"] == 0 and f["measurement_kind"] == "STATISTICAL_SUMMARY"
    assert not any(k in str(f).lower() for k in ("risk", "susceptib", "class_"))


def test_terrain_features_flat_counted_and_empty_is_none_not_zero(tmp_path):
    from affine import Affine
    t = Affine(30, 0, 500000, 0, -30, 1000000)
    flat = write_geotiff(tmp_path / "f.tif", np.full((8, 8), 50.0, dtype="float32"), t, "EPSG:32650", {"units": "metre"})
    ter = compute_terrain(flat, tmp_path / "o")
    f = terrain_features(flat, ter.slope_path, ter.aspect_path, None)
    assert f["flat_pixel_count"] == 36 and f["features"]["aspect_circular_mean"]["value"] is None
    nan = write_geotiff(tmp_path / "n.tif", np.full((8, 8), np.nan, dtype="float32"), t, "EPSG:32650", {"units": "metre"})
    ter2 = compute_terrain(nan, tmp_path / "o2")
    f2 = terrain_features(nan, ter2.slope_path, ter2.aspect_path, None)
    assert f2["features"]["elevation_mean"]["value"] is None and f2["warnings"]


def test_terrain_features_with_aoi(tmp_path):
    t = syn.make_mosaic_tiles(tmp_path / "t")
    aoi = box(116.05, 6.05, 116.15, 6.15)
    dem = prepare_dem([t["tile_a"]], aoi, tmp_path / "o")
    ter = compute_terrain(dem.elevation_path, tmp_path / "o")
    f = terrain_features(dem.elevation_path, ter.slope_path, ter.aspect_path, aoi)
    assert f["valid_pixel_count"] == 100 and f["features"]["elevation_min"]["value"] is not None
