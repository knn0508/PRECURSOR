"""Numerical-oracle tests for Horn slope and aspect. ALL fixtures are SYNTHETIC (app.services.environmental.synthetic_raster):
analytic planes/cones, labelled PRECURSOR_SYNTHETIC_FIXTURE=1. Passing here is NOT real-data validation."""
import numpy as np
import pytest
from affine import Affine
from shapely.geometry import box

from app.services.environmental import synthetic_raster as syn
from app.services.environmental.dem.aspect import (
    aspect_degrees, circular_mean_deg, circular_std_deg, classify_8, resultant_length, sector_histogram)
from app.services.environmental.dem.slope import cell_sizes_m, slope_degrees, slope_percent
from app.services.environmental.raster.io import read_float
from app.services.environmental.types import SYNTHETIC_TAG, EnvError


def _interior(a):
    return a[1:-1, 1:-1]


@pytest.mark.parametrize("deg", [5.0, 30.0, 60.0])
def test_projected_plane_slope_exact(tmp_path, deg):
    z, m = read_float(syn.make_plane(tmp_path / "p.tif", slope_deg=deg))
    s = slope_degrees(z, m.crs, Affine(*m.transform))
    assert np.allclose(_interior(s), deg, atol=1e-4)
    assert np.isnan(s[0]).all() and np.isnan(s[-1]).all() and np.isnan(s[:, 0]).all()  # border is NaN, not 0
    assert m.tags[SYNTHETIC_TAG] == "1"


@pytest.mark.parametrize("az,expected", [(90, 90), (180, 180), (270, 270), (0, 0), (45, 45)])
def test_aspect_convention_clockwise_from_north_downslope(tmp_path, az, expected):
    z, m = read_float(syn.make_plane(tmp_path / "p.tif", slope_deg=20, downslope_azimuth_deg=az))
    res = aspect_degrees(z, m.crs, Affine(*m.transform))
    inner = _interior(res.aspect)
    diff = np.abs((inner - expected + 180) % 360 - 180)  # circular distance (0 and 360 are the same)
    assert diff.max() < 1e-3
    assert inner.max() < 360.0


def test_flat_surface_zero_slope_nan_aspect(tmp_path):
    z = np.full((10, 10), 123.0, dtype=np.float32)
    t = Affine(30, 0, 500000, 0, -30, 1000000)
    s = slope_degrees(z, "EPSG:32650", t)
    assert np.allclose(_interior(s), 0.0)
    res = aspect_degrees(z, "EPSG:32650", t)
    assert np.isnan(res.aspect).all() and res.flat_count == 64 and res.valid_count == 0


@pytest.mark.parametrize("lat0", [0.5, 60.0])
def test_geographic_plane_at_two_latitudes(tmp_path, lat0):
    for az in (90, 180):  # east-west and north-south slopes both need the right metric cell size
        z, m = read_float(syn.make_plane_geographic(tmp_path / f"g{lat0}{az}.tif", lat0=lat0, slope_deg=30,
                                                    downslope_azimuth_deg=az))
        s = slope_degrees(z, m.crs, Affine(*m.transform))
        assert np.allclose(_interior(s), 30.0, atol=0.01), (lat0, az, np.nanmin(s), np.nanmax(s))


def test_degrees_not_treated_as_metres():
    dx, dy = cell_sizes_m("EPSG:4326", Affine(1 / 3600, 0, 116, 0, -1 / 3600, 60.0), 5)
    assert 15.0 < dx[0] < 16.0  # ~30.9 m * cos(60 deg) ~ 15.4 m
    assert 30.0 < dy[0] < 31.5
    dx0, _ = cell_sizes_m("EPSG:4326", Affine(1 / 3600, 0, 116, 0, -1 / 3600, 0.0), 5)
    assert 30.5 < dx0[0] < 31.5


def test_geographic_vs_projected_agree(tmp_path):
    """Same physical plane built independently in UTM and in lat/lon: slopes agree within tolerance."""
    zp, mp = read_float(syn.make_plane(tmp_path / "p.tif", slope_deg=25, downslope_azimuth_deg=135))
    zg, mg = read_float(syn.make_plane_geographic(tmp_path / "g.tif", lat0=6.0, slope_deg=25, downslope_azimuth_deg=135))
    sp = slope_degrees(zp, mp.crs, Affine(*mp.transform))
    sg = slope_degrees(zg, mg.crs, Affine(*mg.transform))
    assert abs(np.nanmean(sp) - np.nanmean(sg)) < 0.05


def test_feet_converted_to_metres():
    # foot-unit CRS (EPSG:2263, US survey foot): 100 ft cells = 30.48006 m; heights (metres) rise 30.48006 m per column
    t = Affine(100.0, 0, 1000000, 0, -100.0, 200000)
    z = np.tile(np.arange(8, dtype=np.float64) * 30.48006096, (8, 1))
    assert np.allclose(_interior(slope_degrees(z, "EPSG:2263", t)), 45.0, atol=0.01)  # 45 only if feet -> metres applied


def test_cone_slope_and_radial_aspect(tmp_path):
    z, m = read_float(syn.make_cone(tmp_path / "c.tif", slope_deg=20, shape=(61, 61)))
    t = Affine(*m.transform)
    s = slope_degrees(z, m.crs, t)
    # Horn smooths a cone only near the apex; away from it the slope is exact
    assert np.allclose(s[30, 40], 20.0, atol=0.1) and np.allclose(s[10, 30], 20.0, atol=0.1)  # Horn is not exact for a cone off-axis
    a = aspect_degrees(z, m.crs, t).aspect
    assert abs(a[30, 45] - 90) < 1e-3  # east of apex faces east
    assert abs(a[45, 30] - 180) < 1e-3  # south of apex faces south
    assert abs(a[30, 15] - 270) < 1e-3
    assert abs((a[15, 30] - 0 + 180) % 360 - 180) < 1e-3


def test_nodata_neighbours_give_nan_not_zero(tmp_path):
    z, m = read_float(syn.make_noisy_terrain(tmp_path / "n.tif"))
    t = Affine(*m.transform)
    s = slope_degrees(z, m.crs, t)
    a = aspect_degrees(z, m.crs, t).aspect
    assert np.isnan(s[19:31, 24:36]).all()  # hole (20:30,25:35) plus one ring of neighbours
    assert np.isnan(a[19:31, 24:36]).all()
    assert np.isfinite(s[5:15, 5:15]).all() and (s[5:15, 5:15] > 0).all()


def test_unsupported_crs_and_missing_crs():
    with pytest.raises(EnvError):
        cell_sizes_m("", Affine(1, 0, 0, 0, -1, 0), 3)
    with pytest.raises(EnvError):
        cell_sizes_m("EPSG:4326", Affine(1, 0.1, 0, 0, -1, 0), 3)


def test_slope_percent():
    assert np.isclose(slope_percent(np.array([45.0, np.nan], dtype=np.float32))[0], 100.0, atol=1e-3)
    assert np.isnan(slope_percent(np.array([np.nan], dtype=np.float32))[0])


# ---- circular statistics ----
def test_circular_mean_wraps_across_north():
    assert min(circular_mean_deg(np.array([359.0, 1.0])), 360 - circular_mean_deg(np.array([359.0, 1.0]))) < 1e-6
    assert abs(circular_mean_deg(np.array([350.0, 10.0, 0.0])) % 360) < 1e-6 or circular_mean_deg(np.array([350.0, 10.0, 0.0])) > 359.999


def test_resultant_length_and_std():
    assert np.isclose(resultant_length(np.array([90.0, 90.0, 90.0])), 1.0)
    assert resultant_length(np.array([0.0, 180.0])) < 1e-9
    assert circular_mean_deg(np.array([0.0, 180.0])) is None  # undefined, not 0
    assert circular_std_deg(np.array([90.0, 90.0])) < 1e-3
    assert circular_mean_deg(np.array([np.nan])) is None and resultant_length(np.array([])) is None


def test_classify_8_and_histogram():
    a = np.array([0, 22.4, 22.6, 90, 180, 270, 337.4, 337.6, 359.9, np.nan])
    assert classify_8(a).tolist() == [0, 0, 1, 2, 4, 6, 7, 0, 0, -1]
    h = sector_histogram(a)
    assert h["N"] == 4 and h["NE"] == 1 and sum(h.values()) == 9  # NaN excluded, not counted anywhere
