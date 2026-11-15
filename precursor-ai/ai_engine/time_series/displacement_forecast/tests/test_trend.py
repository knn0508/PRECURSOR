"""Tests required by precursor_ai_skill_v2.md (trend-first forecasting)."""
import numpy as np
import pandas as pd
import pytest

from displacement_forecast.causal_velocity import ols, theil_sen, huber
from displacement_forecast.kalman_trend import filter_series
from displacement_forecast.trend_target_144d import future_slope


def _series(T=60, P=200, v=-0.1, sd=2.0, seed=0, dt=12.0):
    rng = np.random.default_rng(seed)
    td = np.arange(T) * dt
    s = (v * td)[:, None] * np.ones((1, P))
    return td, s, s + rng.normal(0, sd, (T, P))


def test_shared_endpoint_noise_gives_minus_half_lag1_correlation():
    td, s, z = _series(T=400, P=500, v=0.0, sd=2.0)
    inc = np.diff(z, axis=0)
    a, b = inc[1:].ravel(), inc[:-1].ravel()
    assert abs(np.corrcoef(a, b)[0, 1] + 0.5) < 0.02          # white level noise -> -0.5
    inc24 = z[2::2] - z[:-2:2]                                  # non-overlapping 24-day increments, shared endpoint again
    c = np.corrcoef(inc24[1:].ravel(), inc24[:-1].ravel())[0, 1]
    assert abs(c + 0.5) < 0.03
    disjoint = (z[3::4] - z[2::4])[: (z.shape[0] - 3) // 4]    # increments with no shared endpoint
    d = np.corrcoef(disjoint[1:].ravel(), disjoint[:-1].ravel())[0, 1]
    assert abs(d) < 0.03


@pytest.mark.parametrize("est", [ols, theil_sen, huber])
def test_causal_history_only(est):
    td, s, z = _series()
    a = est(z, td, 144.0)
    z2 = z.copy(); z2[40:] += 500.0                             # change only dates >= 40
    b = est(z2, td, 144.0)
    for k in ("vel", "level", "resid"):
        assert np.allclose(np.nan_to_num(a[k][:40]), np.nan_to_num(b[k][:40]))


def test_kalman_is_one_sided():
    td, s, z = _series()
    a = filter_series(z, td, R=4.0, q=1e-5)
    z2 = z.copy(); z2[30:] -= 300.0
    b = filter_series(z2, td, R=4.0, q=1e-5)
    assert np.allclose(a["vel"][:30], b["vel"][:30]) and np.allclose(a["level"][:30], b["level"][:30])


def test_irregular_date_intervals_use_real_days():
    rng = np.random.default_rng(1)
    td = np.cumsum(rng.choice([6.0, 12.0, 24.0, 36.0], 50)); td -= td[0]
    z = (0.2 * td)[:, None] * np.ones((1, 10))                   # exact line, irregular sampling
    for est in (ols, theil_sen, huber):
        o = est(z, td, 200.0, min_n=4, min_span=30.0)
        assert np.allclose(o["vel"][20:], 0.2, atol=1e-6)
    k = filter_series(z, td, R=0.01, q=1e-8)
    assert np.allclose(k["vel"][-1], 0.2, atol=5e-3)


def test_masked_finite_values_are_not_labels():
    td, s, z = _series(T=40, P=5)
    obs = z.copy(); obs[25:35, 0] = np.nan                       # masked-but-finite -> passed as NaN
    lab = future_slope(obs, td, np.array([20, 20]), np.array([0, 1]), window=144.0)
    poisoned = obs.copy(); poisoned[25:35, 0] = 1e6              # if masked values leaked in, label would explode
    lab2 = future_slope(np.where(np.isnan(obs), np.nan, poisoned), td, np.array([20, 20]), np.array([0, 1]))
    assert np.allclose(lab["slope"], lab2["slope"], equal_nan=True)
    sparse = obs.copy(); sparse[21:, 2] = np.nan
    lab3 = future_slope(sparse, td, np.array([20]), np.array([2]))
    assert np.isnan(lab3["slope"][0])                            # unscorable, never filled


def test_true_reversal_is_not_forbidden():
    td = np.arange(80) * 12.0
    s = np.where(td < 480, -0.2 * td, -0.2 * 480 + 0.3 * (td - 480))  # real reversal at day 480
    z = s[:, None] + np.random.default_rng(3).normal(0, 1.0, (80, 50))
    k = filter_series(z, td, R=1.0, q=1e-5)
    o = huber(z, td, 144.0)
    assert np.median(k["vel"][35]) < 0 and np.median(k["vel"][-1]) > 0.2   # both signs reachable
    assert np.median(o["vel"][35]) < 0 and np.median(o["vel"][-1]) > 0.2


def test_robust_slope_resists_isolated_phase_jump():
    td, s, z = _series(T=40, P=100, v=0.1, sd=0.5)
    zj = z.copy(); zj[30] += 28.0                                # one unwrapping-like jump (~lambda/2 C-band)
    ts, ol = theil_sen(zj, td, 144.0), ols(zj, td, 144.0)
    err_ts = np.abs(np.median(ts["vel"][32]) - 0.1); err_ol = np.abs(np.median(ol["vel"][32]) - 0.1)
    assert err_ts < err_ol


def test_target_144d_uses_future_only():
    td, s, z = _series(T=50, P=3, v=0.15, sd=0.1)
    a = future_slope(z, td, np.array([20]), np.array([0]))
    z2 = z.copy(); z2[:21] += 999.0                              # change past and the issue date itself
    b = future_slope(z2, td, np.array([20]), np.array([0]))
    assert np.allclose(a["slope"], b["slope"]) and abs(a["slope"][0] - 0.15) < 0.01


def test_trend_baseline_selection_uses_validation_only():
    from displacement_forecast.trend_selection import select_on_validation
    rows = pd.DataFrame({"model": ["a", "b"], "val_MAE": [3.0, 2.9], "test_MAE": [2.0, 2.5]})
    assert select_on_validation(rows, "val_MAE")["model"] == "b"  # test column ignored


def test_calibration_groups_have_no_oracle_input():
    from displacement_forecast.trend_selection import conformal_groups
    pred = np.array([0.1, 5.0, -3.0, 0.0]); label = np.array([100.0, 0.0, 0.0, -50.0])
    g1 = conformal_groups(pred_abs=np.abs(pred), moving=np.array([0, 1, 0, 1], bool), edges=[1.0, 4.0])
    g2 = conformal_groups(pred_abs=np.abs(pred), moving=np.array([0, 1, 0, 1], bool), edges=[1.0, 4.0])
    assert np.array_equal(g1, g2)
    import inspect
    assert "label" not in inspect.signature(conformal_groups).parameters and "y" not in inspect.signature(conformal_groups).parameters
