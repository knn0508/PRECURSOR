"""Pure scientific functions with hand-computed expectations. All inputs are SYNTHETIC arrays."""
import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.services.insar import coherence as coh
from app.services.insar import interferogram as ifg
from app.services.insar import phase_to_displacement as p2d
from app.services.insar import velocity as vel

LAM = 0.24  # metres, round number for hand arithmetic


# --- phase -> displacement ---------------------------------------------------------------------
def test_one_fringe_is_half_wavelength():
    d = p2d.phase_to_los_displacement_m(np.array([2 * math.pi]), LAM)
    assert d[0] == pytest.approx(-LAM / 2)  # 2*pi rad -> -lambda/2 under d = -(lambda/4pi)*phi


def test_sign_zero_and_linearity():
    phi = np.array([-math.pi, 0.0, math.pi, 2 * math.pi])
    d = p2d.phase_to_los_displacement_m(phi, LAM)
    assert d[1] == 0.0
    assert d[0] == pytest.approx(LAM / 4) and d[2] == pytest.approx(-LAM / 4)
    assert d[3] == pytest.approx(2 * d[2])


def test_nan_and_inf_stay_missing_never_zero():
    d = p2d.phase_to_los_displacement_m(np.array([np.nan, np.inf, -np.inf, 1.0]), LAM)
    assert np.isnan(d[:3]).all() and np.isfinite(d[3])


def test_wavelength_from_frequency_and_validation():
    assert p2d.wavelength_from_frequency(1_257_500_000.0) == pytest.approx(0.23840, abs=1e-4)
    for bad in (0.0, -1.0, float("nan")):
        with pytest.raises(ValueError):
            p2d.wavelength_from_frequency(bad)
    with pytest.raises(ValueError):
        p2d.validate_wavelength(24.0)  # centimetres mistaken for metres


def test_round_trip_with_phase_per_displacement():
    k = p2d.phase_per_displacement_rad_per_m(LAM)
    assert k == pytest.approx(4 * math.pi / LAM)
    d = np.array([0.01])  # 1 cm toward satellite
    phi = -k * d
    assert p2d.phase_to_los_displacement_m(phi, LAM)[0] == pytest.approx(0.01)


def test_sign_convention_is_declared_unverified():
    assert p2d.SIGN_CONVENTION_VERIFIED is False


# --- coherence -----------------------------------------------------------------------------------
def test_valid_coherence_mask():
    c = np.array([0.0, 0.5, 1.0, 1.5, -0.5, np.nan, -9999.0])
    assert coh.valid_coherence_mask(c, fill_value=-9999.0).tolist() == [True, True, True, False, False, False, False]


def test_coherence_accumulator_matches_numpy_across_blocks():
    rng = np.random.default_rng(0)
    c = rng.uniform(0, 1, (40, 30))
    c[0, 0] = np.nan
    acc = coh.CoherenceAccumulator(threshold=0.5)
    for r in range(0, 40, 7):
        acc.update(c[r : r + 7])
    out = acc.result()
    ok = np.isfinite(c)
    assert out["valid_pixels"] == ok.sum() and out["invalid_pixels"] == 1
    assert out["mean"] == pytest.approx(c[ok].mean())
    assert out["fraction_below_threshold"] == pytest.approx((c[ok] < 0.5).mean())


def test_estimate_coherence_identical_is_one_and_independent_is_low():
    rng = np.random.default_rng(1)
    a = rng.normal(size=(64, 64)) + 1j * rng.normal(size=(64, 64))
    assert coh.estimate_coherence(a, a, 5) == pytest.approx(np.ones((64, 64)))
    b = rng.normal(size=(64, 64)) + 1j * rng.normal(size=(64, 64))
    assert coh.estimate_coherence(a, b, 9)[8:-8, 8:-8].mean() < 0.3  # bias exists at small windows; just "low"


def test_estimate_coherence_phase_ramp_stays_one():
    x = np.arange(32)[None, :] * np.ones((32, 1))
    a = np.exp(1j * 0.3 * x)
    # Exact oracle: boxcar mean of exp(j*0.3*k) over 3 samples has magnitude (1 + 2*cos(0.3)) / 3.
    expected = (1 + 2 * math.cos(0.3)) / 3
    assert coh.estimate_coherence(a, np.ones_like(a), 3)[1:-1, 1:-1] == pytest.approx(expected)


def test_estimate_coherence_rejects_bad_input():
    with pytest.raises(ValueError):
        coh.estimate_coherence(np.ones((4, 4), complex), np.ones((5, 5), complex))
    with pytest.raises(ValueError):
        coh.estimate_coherence(np.ones((4, 4), complex), np.ones((4, 4), complex), window=4)


# --- interferogram ---------------------------------------------------------------------------------
def test_wrapped_interferogram_recovers_known_phase_difference():
    s1 = np.exp(1j * np.full((4, 4), 1.0))
    s2 = np.exp(1j * np.full((4, 4), 0.25))
    assert ifg.wrapped_phase(ifg.wrapped_interferogram(s1, s2)) == pytest.approx(np.full((4, 4), 0.75))


def test_wrap_range_and_zero_amplitude_is_nan():
    w = ifg.wrap(np.array([0.0, math.pi, 3 * math.pi, -3 * math.pi, 2 * math.pi + 0.1]))
    assert (w > -math.pi - 1e-12).all() and (w <= math.pi + 1e-12).all()
    assert w[-1] == pytest.approx(0.1)
    z = ifg.wrapped_phase(np.array([[0j, 1j]]))
    assert np.isnan(z[0, 0]) and z[0, 1] == pytest.approx(math.pi / 2)


def test_interferogram_requires_complex_same_shape():
    with pytest.raises(ValueError):
        ifg.wrapped_interferogram(np.ones((2, 2)), np.ones((2, 2)))
    with pytest.raises(ValueError):
        ifg.wrapped_interferogram(np.ones((2, 2), complex), np.ones((3, 3), complex))


# --- velocity -----------------------------------------------------------------------------------------
T0 = datetime(2025, 10, 1, tzinfo=UTC)


def test_velocity_units_mm_per_year():
    v = vel.interferogram_mean_velocity(np.array([10.0]), T0, T0 + timedelta(days=12))
    assert v[0] == pytest.approx(10.0 / (12 / 365.25))  # 304.375 mm/year


def test_velocity_requires_chronological_dates():
    for t_sec in (T0, T0 - timedelta(days=1), None):
        with pytest.raises(vel.IncompatibleProducts):
            vel.interferogram_mean_velocity(np.array([1.0]), T0, t_sec)
    with pytest.raises(vel.IncompatibleProducts):
        vel.interferogram_mean_velocity(np.array([1.0]), None, T0)


def _meta(**kw):
    base = dict(reference_time=T0, secondary_time=T0 + timedelta(days=12), width=10, height=10,
                transform=(80.0, 0.0, 5e5, 0.0, -80.0, 4e6), crs="EPSG:32618", orbit_direction="Ascending", relative_orbit=7)
    base.update(kw)
    return vel.DisplacementMeta(**base)


def test_velocity_between_products_ok_and_value():
    a, b = _meta(), _meta(secondary_time=T0 + timedelta(days=24))
    v = vel.velocity_between_products(np.array([5.0]), np.array([11.0]), a, b)
    assert v[0] == pytest.approx(6.0 / (12 / 365.25))


@pytest.mark.parametrize("change", [
    dict(width=11), dict(crs="EPSG:4326"), dict(orbit_direction="Descending"), dict(orbit_direction=None),
    dict(relative_orbit=8), dict(reference_time=T0 + timedelta(days=1)), dict(units="m"),
    dict(transform=(80.0, 0.0, 5e5 + 80, 0.0, -80.0, 4e6)),
])
def test_velocity_between_products_rejects_incompatible(change):
    a = _meta()
    b = _meta(secondary_time=T0 + timedelta(days=24), **change)
    with pytest.raises(vel.IncompatibleProducts):
        vel.velocity_between_products(np.array([1.0]), np.array([2.0]), a, b)


def test_velocity_between_products_rejects_wrong_order():
    a, b = _meta(secondary_time=T0 + timedelta(days=24)), _meta()
    with pytest.raises(vel.IncompatibleProducts):
        vel.velocity_between_products(np.array([1.0]), np.array([2.0]), a, b)
