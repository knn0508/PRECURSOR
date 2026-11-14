"""Clipping, mosaic and alignment tests. ALL fixtures are SYNTHETIC (tagged PRECURSOR_SYNTHETIC_FIXTURE=1); not real data."""
import numpy as np
import pytest
from affine import Affine
from shapely.geometry import MultiPolygon, Point, Polygon, box

from app.services.environmental import synthetic_raster as syn
from app.services.environmental.raster.alignment import TargetGrid, align_array, resampling_for
from app.services.environmental.raster.clipping import clip_raster
from app.services.environmental.raster.io import inspect_raster, read_float, write_geotiff
from app.services.environmental.raster.mosaic import mosaic_rasters
from app.services.environmental.types import SYNTHETIC_TAG, EnvError, LayerKind, NotAvailable
from rasterio.warp import Resampling


# ---------------- clipping ----------------
def test_clip_full_inside_geographic(tmp_path):
    tiles = syn.make_mosaic_tiles(tmp_path)
    aoi = box(116.05, 6.05, 116.15, 6.15)
    r = clip_raster(tiles["tile_a"], aoi, tmp_path / "out.tif")
    assert r.coverage_percent == pytest.approx(100.0)
    assert r.array.dtype == np.float32 and r.array.shape == (10, 10)
    out = inspect_raster(tmp_path / "out.tif")
    assert out.is_synthetic and out.units == "metre" and np.isnan(out.nodata)


def test_clip_partial_overlap_reports_coverage(tmp_path):
    tiles = syn.make_mosaic_tiles(tmp_path)  # tile_a spans lon 116.00-116.20
    r = clip_raster(tiles["tile_a"], box(116.10, 6.05, 116.30, 6.15))  # half of AOI is outside the source
    assert r.coverage_percent == pytest.approx(50.0, abs=0.01)
    assert any("covers only" in w for w in r.warnings)


def test_clip_polygon_mask_makes_outside_nan(tmp_path):
    tiles = syn.make_mosaic_tiles(tmp_path)
    tri = Polygon([(116.02, 6.02), (116.18, 6.02), (116.02, 6.18)])
    r = clip_raster(tiles["tile_a"], tri)
    assert np.isnan(r.array).any() and np.isfinite(r.array).any()
    assert not (r.array == 0).any()
    assert r.valid_in_aoi_percent == pytest.approx(100.0)  # NaNs are outside the polygon, not inside it


def test_clip_no_overlap_not_available(tmp_path):
    tiles = syn.make_mosaic_tiles(tmp_path)
    with pytest.raises(NotAvailable):
        clip_raster(tiles["tile_a"], box(10, 10, 11, 11))


def test_clip_invalid_geometry(tmp_path):
    tiles = syn.make_mosaic_tiles(tmp_path)
    bowtie = Polygon([(116, 6), (116.1, 6.1), (116.1, 6), (116, 6.1)])
    for bad in (bowtie, Point(116.1, 6.1), Polygon(), box(170, 0, 190, 5)):
        with pytest.raises(EnvError):
            clip_raster(tiles["tile_a"], bad)


def test_clip_projected_crs_transform_and_multipolygon(tmp_path):
    p = syn.make_plane(tmp_path / "p.tif", shape=(60, 60))  # UTM 50N, 30 m
    # AOI near lon 117E (UTM50 central meridian), lat ~9.05N, matches x 500000 / y 1000000
    from pyproj import Transformer
    lon, lat = Transformer.from_crs("EPSG:32650", "EPSG:4326", always_xy=True).transform(500_500, 999_500)
    d = 0.002
    mp = MultiPolygon([box(lon, lat, lon + d, lat + d), box(lon + 0.004, lat, lon + 0.006, lat + d)])
    r = clip_raster(p, mp)
    assert r.crs == "EPSG:32650" and r.coverage_percent == pytest.approx(100.0, abs=0.01)
    assert np.isnan(r.array).any()  # gap between the two parts of the MultiPolygon is NaN


def test_clip_missing_crs_refused(tmp_path):
    from tests.environmental.test_raster_io_quality import _no_crs_tif
    with pytest.raises(EnvError):
        clip_raster(_no_crs_tif(tmp_path / "x.tif"), box(0, 0, 1, 1))


# ---------------- mosaic ----------------
def test_mosaic_overlap_agrees_and_missing_tile_reported(tmp_path):
    t = syn.make_mosaic_tiles(tmp_path)
    m = mosaic_rasters([t["tile_c"], t["tile_a"], t["tile_b"]], dst=tmp_path / "m.tif")
    assert m.array.shape == (20, 75)
    assert m.overlap_pixels == 5 * 20 and m.overlap_max_abs_diff < 1e-3
    assert m.gap_percent_of_extent == pytest.approx(100 * 20 / 75, abs=0.01)  # the missing tile columns
    assert np.isnan(m.array[:, 35:55]).all()  # never filled
    assert any("covered by no tile" in w for w in m.warnings) and any("more than one tile" in w for w in m.warnings)
    assert not any("DISAGREE" in w for w in m.warnings)
    lon = 116.0 + (np.arange(75) + 0.5) * 0.01
    lat = 6.2 - (np.arange(20) + 0.5) * 0.01
    expect = syn.tile_value(*np.meshgrid(lon, lat))
    ok = np.isfinite(m.array)
    assert np.allclose(m.array[ok], expect[ok], atol=1e-3)
    assert inspect_raster(tmp_path / "m.tif").is_synthetic


def test_mosaic_overlap_disagreement_warns_and_is_deterministic(tmp_path):
    t = syn.make_mosaic_tiles(tmp_path, disagree_overlap=True)
    m1 = mosaic_rasters([t["tile_a"], t["tile_b"]])
    m2 = mosaic_rasters([t["tile_b"], t["tile_a"]])
    assert m1.overlap_max_abs_diff == pytest.approx(5.0) and any("DISAGREE" in w for w in m1.warnings)
    assert np.array_equal(m1.array, m2.array, equal_nan=True)  # input order does not matter
    assert m1.array[0, 17] == pytest.approx(float(syn.tile_value(np.array(116.175), np.array(6.195))), abs=1e-3)  # tile_a wins


def test_mosaic_warns_on_units_and_datum(tmp_path):
    t = syn.make_mosaic_tiles(tmp_path)
    m = mosaic_rasters([t["tile_a"], t["tile_b"]])
    assert m.tags["units"] == "metre" and m.tags["vertical_datum"] == "SYNTHETIC_DATUM"
    z, meta = read_float(t["tile_c"])
    nounits = write_geotiff(tmp_path / "nu.tif", z, Affine(*meta.transform), meta.crs, {})
    m2 = mosaic_rasters([t["tile_a"], nounits])
    assert any("units not declared" in w for w in m2.warnings) and any("vertical datum declared for some" in w for w in m2.warnings)
    ft = write_geotiff(tmp_path / "ft.tif", z, Affine(*meta.transform), meta.crs, {"units": "foot"})
    assert any("mixed units" in w for w in mosaic_rasters([t["tile_a"], ft]).warnings)


def test_mosaic_mixed_crs_and_resolution_rejected_or_aligned(tmp_path):
    t = syn.make_mosaic_tiles(tmp_path)
    proj = syn.make_plane(tmp_path / "utm.tif", shape=(20, 20))
    with pytest.raises(EnvError, match="mixed CRS"):
        mosaic_rasters([t["tile_a"], proj])
    z, meta = read_float(t["tile_a"])
    coarse = write_geotiff(tmp_path / "coarse.tif", z[::2, ::2], Affine(0.02, 0, 116.0, 0, -0.02, 6.2), "EPSG:4326", {})
    with pytest.raises(EnvError, match="mixed resolution"):
        mosaic_rasters([t["tile_a"], coarse])
    grid = TargetGrid("EPSG:4326", Affine(0.01, 0, 116.0, 0, -0.01, 6.2), 35, 20)
    m = mosaic_rasters([t["tile_a"], coarse], target_grid=grid)
    assert m.array.shape == (20, 35) and any("target grid" in w for w in m.warnings)


def test_mosaic_misaligned_rejected(tmp_path):
    t = syn.make_mosaic_tiles(tmp_path)
    z, _ = read_float(t["tile_b"])
    shifted = write_geotiff(tmp_path / "s.tif", z, Affine(0.01, 0, 116.0 + 0.0033, 0, -0.01, 6.2), "EPSG:4326", {})
    with pytest.raises(EnvError, match="pixel-aligned"):
        mosaic_rasters([t["tile_a"], shifted])


def test_mosaic_empty_and_single(tmp_path):
    with pytest.raises(EnvError):
        mosaic_rasters([])
    t = syn.make_mosaic_tiles(tmp_path)
    assert mosaic_rasters([t["tile_a"]]).overlap_pixels == 0


# ---------------- alignment ----------------
def test_resampling_rules():
    assert resampling_for(LayerKind.LAND_COVER) == Resampling.nearest
    for k in (LayerKind.ELEVATION, LayerKind.SLOPE, LayerKind.SOIL, LayerKind.RAINFALL):
        assert resampling_for(k) == Resampling.bilinear


def test_categorical_nearest_preserves_class_ids(tmp_path):
    z, m = read_float(syn.make_land_cover(tmp_path / "lc.tif"))
    t = Affine(*m.transform)
    # finer, shifted, non-integer-ratio grid: bilinear would invent values between the class ids
    grid = TargetGrid(m.crs, Affine(7.3, 0, 500_000 + 2.1, 0, -7.3, 1_000_000 - 1.7), 60, 60)
    r = align_array(z, t, m.crs, m.resolution(), grid, LayerKind.LAND_COVER)
    ids = set(np.unique(r.array[np.isfinite(r.array)]).tolist())
    assert ids <= {10.0, 20.0, 30.0, 40.0} and len(ids) == 4  # no new ids
    rb = align_array(z, t, m.crs, m.resolution(), grid, LayerKind.ELEVATION)
    assert not set(np.unique(rb.array[np.isfinite(rb.array)]).tolist()) <= {10.0, 20.0, 30.0, 40.0}  # contrast: bilinear invents
    assert any("information" in w for w in r.warnings)


def test_aspect_alignment_is_circular(tmp_path):
    t = Affine(1.0, 0, 0, 0, -1.0, 8)
    asp = np.where(np.arange(8) % 2 == 0, 359.0, 1.0)[None, :].repeat(8, 0).astype(np.float32)
    grid = TargetGrid("EPSG:32650", Affine(2.0, 0, 0, 0, -2.0, 8), 4, 4)
    r = align_array(asp, t, "EPSG:32650", {"x": 1, "y": 1, "unit": "crs_linear_unit"}, grid, LayerKind.ASPECT)
    d = np.abs((r.array - 0 + 180) % 360 - 180)
    assert np.nanmax(d) < 1.0  # ~0/360, not ~180 as raw bilinear would give
    assert r.array[np.isfinite(r.array)].max() < 360


def test_aspect_alignment_preserves_nan_and_cancellation():
    t = Affine(1.0, 0, 0, 0, -1.0, 4)
    asp = np.full((4, 4), np.nan, dtype=np.float32)
    asp[:, :2] = 90.0
    asp[:, 2:] = 270.0
    grid = TargetGrid("EPSG:32650", Affine(4.0, 0, 0, 0, -4.0, 4), 1, 1)
    r = align_array(asp, t, "EPSG:32650", {"x": 1, "y": 1, "unit": "crs_linear_unit"}, grid, LayerKind.ASPECT)
    assert np.isnan(r.array).all() and any("cancel" in w for w in r.warnings)  # undefined, not 0 or 180


def test_bilinear_continuous_and_nodata_and_reports(tmp_path):
    z, m = read_float(syn.make_plane(tmp_path / "p.tif", shape=(20, 20)))
    grid = TargetGrid(m.crs, Affine(15, 0, 500_000, 0, -15, 1_000_000), 40, 40)
    r = align_array(z, Affine(*m.transform), m.crs, m.resolution(), grid, LayerKind.ELEVATION)
    assert r.native_resolution["x"] == 30 and r.processing_resolution["x"] == 15
    assert any("does not add information" in w for w in r.warnings)
    from rasterio.crs import CRS
    with pytest.raises(EnvError):
        align_array(z, Affine(*m.transform), "", m.resolution(), grid, LayerKind.ELEVATION)
