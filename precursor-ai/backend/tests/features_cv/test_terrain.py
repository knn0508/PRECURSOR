"""Terrain feature oracles on SYNTHETIC arrays (analytic cases). Not real-data validation."""
import numpy as np
import pytest
from affine import Affine

from app.services.environmental.dem.slope import cell_sizes_m, horn_gradients
from app.services.features_cv import terrain as T
from app.services.features_cv.tiling import tiled_apply
from app.services.features_cv.types import FeatureError

RES = 30.0
N = 41


def grid(fn):
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float64)
    return fn(xx * RES, yy * RES).astype(np.float32)


def cs(n=N):
    return np.full(n, RES), np.full(n, RES)


def test_local_relief_on_a_plane_is_gradient_times_span():
    g = 0.2  # m/m along x
    z = grid(lambda x, y: g * x)
    out = T.local_relief(z, 5)
    assert out[20, 20] == pytest.approx(g * RES * 4, rel=1e-6)
    flat = T.local_relief(np.full((N, N), 7.0, np.float32), 5)
    assert np.nanmax(flat) == 0.0 and not np.isnan(flat[20, 20])


def test_local_relief_min_valid_fraction_and_nan_centre():
    z = grid(lambda x, y: x * 0.1)
    z[18:23, 18:23] = np.nan
    out = T.local_relief(z, 5)
    assert np.isnan(out[20, 20])  # NaN centre -> NaN, never 0
    assert not np.isnan(out[30, 30])


def test_tri_on_a_plane_matches_riley_formula():
    g = 0.15
    z = grid(lambda x, y: g * x)
    out = T.terrain_ruggedness(z)
    assert out[20, 20] == pytest.approx(np.sqrt(6) * g * RES, rel=1e-5)
    assert np.isnan(out[0, :]).all() and np.isnan(out[:, 0]).all()  # border undefined


def test_curvature_of_a_paraboloid_is_4k():
    k = 1e-3
    z = grid(lambda x, y: k * ((x - 600) ** 2 + (y - 600) ** 2))
    dx, dy = cs()
    c = T.curvature_laplacian(z, dx, dy, 0.0)
    assert c[20, 20] == pytest.approx(4 * k, rel=1e-3)  # Laplacian of k(x^2+y^2) = 4k; positive = concave-up
    ridge = T.curvature_laplacian(-z, dx, dy, 0.0)
    assert ridge[20, 20] == pytest.approx(-4 * k, rel=1e-3)


def test_curvature_of_a_plane_is_zero_with_and_without_smoothing():
    z = grid(lambda x, y: 0.3 * x + 0.1 * y)
    dx, dy = cs()
    assert np.nanmax(np.abs(T.curvature_laplacian(z, dx, dy, 0.0))) < 1e-5
    sm = T.curvature_laplacian(z, dx, dy, 1.5)
    assert abs(sm[20, 20]) < 1e-5


def test_smoothing_never_extends_data_into_missing_cells():
    z = grid(lambda x, y: x * 0.1)
    z[10:15, 10:15] = np.nan
    s = T.gaussian_smooth(z, 1.0)
    assert np.isnan(s[12, 12])
    assert T.gaussian_smooth(z, 0.0)[30, 30] == pytest.approx(z[30, 30])


def test_slope_break_of_a_linear_slope_ramp():
    s = 0.01  # deg per metre
    slope = grid(lambda x, y: 5 + s * x)
    dx, dy = cs()
    out = T.slope_break(slope, dx, dy)
    assert out[20, 20] == pytest.approx(s, rel=1e-4)
    assert np.isnan(out[0, 5])


def test_lineament_density_responds_to_a_scarp_and_is_zero_on_a_plane():
    n = 80
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    z = np.where(xx > 40, 25.0, 0.0).astype(np.float32)  # a vertical scarp (step) at column 40
    dx, dy = np.full(n, RES), np.full(n, RES)
    gx, gy = horn_gradients(z, dx, dy)
    dens, edges = T.lineament_density(gx, gy, 9, azimuths=(0.0, 90.0, 180.0, 270.0))
    assert np.nanmax(dens[20:60, 38:43]) > 0.05
    assert np.nanmax(dens[20:60, 5:15]) == 0.0
    gx2, gy2 = horn_gradients((xx * 0.1).astype(np.float32), dx, dy)
    d2, _ = T.lineament_density(gx2, gy2, 9)
    assert np.nanmax(d2) == 0.0  # a uniform plane has no edges
    assert ((edges == 0) | (edges == 1) | np.isnan(edges)).all()


def test_hillshade_known_values():
    zero = np.zeros((3, 3), np.float32)
    assert T.hillshade(zero, zero, 315, 45)[1, 1] == pytest.approx(np.sin(np.radians(45)), rel=1e-6)
    gx = np.full((3, 3), 0.5, np.float32)  # rises toward east -> faces west
    assert T.hillshade(gx, zero, 270, 45)[1, 1] > T.hillshade(gx, zero, 90, 45)[1, 1]


@pytest.mark.parametrize("fn,halo", [
    (lambda b, r0: T.local_relief(b, 5), 2),
    (lambda b, r0: T.terrain_ruggedness(b), 1),
    (lambda b, r0: T.curvature_laplacian(b, *cs(b.shape[0]), 1.0), 5),
])
def test_tiled_result_equals_whole_array(fn, halo):
    rng = np.random.default_rng(3)
    z = (rng.normal(0, 2, (N, N)) + np.arange(N)[None, :] * 0.3).astype(np.float32)
    z[5:8, 30:33] = np.nan
    whole = fn(z, 0)
    tiled = tiled_apply(z, fn, tile=13, halo=halo)
    assert np.allclose(whole, tiled, equal_nan=True, atol=1e-6)


def test_slope_break_tiled_with_row_dependent_cell_sizes_equals_whole():
    rng = np.random.default_rng(4)
    s = rng.uniform(0, 40, (N, N)).astype(np.float32)
    dx = np.linspace(28, 32, N)
    dy = np.linspace(29, 31, N)
    whole = T.slope_break(s, dx, dy)
    tiled = tiled_apply(s, lambda b, r0: T.slope_break(b, dx[r0:r0 + b.shape[0]], dy[r0:r0 + b.shape[0]]), tile=11, halo=1)
    assert np.allclose(whole, tiled, equal_nan=True, atol=1e-7)


def test_input_validation():
    z = np.zeros((10, 10), np.float32)
    for bad in (2, 4, 0, -3, True):
        with pytest.raises(FeatureError):
            T.local_relief(z, bad)
    with pytest.raises(FeatureError):
        T.local_relief(z, 5, 0)
    with pytest.raises(FeatureError):
        T.gaussian_smooth(z, float("nan"))
    with pytest.raises(FeatureError):
        T.curvature_laplacian(z, np.ones(3), np.ones(3))
    tiny = np.zeros((2, 2), np.float32)
    assert np.isnan(T.terrain_ruggedness(tiny)).all() and np.isnan(T.curvature_laplacian(tiny, np.ones(2), np.ones(2))).all()
    with pytest.raises(FeatureError):
        T.local_relief(np.zeros(5, np.float32), 3)


def test_cell_sizes_helper_is_reused_for_geographic_grids():
    dx, dy = cell_sizes_m("EPSG:4326", Affine(1 / 3600, 0, 116.0, 0, -1 / 3600, 5.2), 4)
    assert 29.0 < dx[0] < 32.0 and 29.0 < dy[0] < 32.0  # ~30 m near the equator, not 1/3600 "metres"
