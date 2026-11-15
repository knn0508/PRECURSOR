"""Skill v3 mandatory tests (1-15). Tests needing absent inputs SKIP with an explicit reason, never pass."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from displacement_forecast.conditional_decomposition import eu_zero_north, north_leakage
from displacement_forecast.geometry_alignment import (obs_class, valid_only, coverage_classes, block_to_grid, categorical_to_grid,
                                          match_intervals, interval_from_ministack, admissible_at, assert_same_grid)
from displacement_forecast.los_geometry import identifiability, project, los_from_xy, check_unit, GeometryError
from displacement_forecast.nisar_validation import apply_phase_corrections, DoubleCorrectionError, signed_los_mm, SIGN_STATUS
from displacement_forecast.observability_flags import issue_state, MASKED
from displacement_forecast.physics_checks import phase_to_los_mm, check_sensor_comparison, SensorComparisonError
from displacement_forecast.product_schema import record, from_observation
from displacement_forecast.state_space_deformation import SSConfig, run_filter, forecast_increment

ROOT = Path(__file__).resolve().parents[4] / "data" / "displacement_forecast"
V3 = ROOT / "results_v3"
ASC = np.array([-0.54296875, -0.1029052734375, 0.833984375])     # F16940 static layer, AOI median (verified file)
DESC = np.array([0.65625, -0.11474609375, 0.74609375])            # F18904 static layer, AOI median (verified file)


def _series(T=60, P=5, seed=0, v=-0.05, R=4.0):
    rng = np.random.default_rng(seed)
    td = np.cumsum(rng.choice([6.0, 12.0, 24.0], T)); td -= td[0]
    y = v * td[:, None] + rng.normal(0, np.sqrt(R), (T, P))
    return y, td


# 1
def test_masked_but_finite_never_becomes_truth():
    disp = np.array([1.0, 2.0, np.nan, 4.0]); rm = np.array([1, 0, 0, 1])
    c = obs_class(disp, rm)
    assert list(c) == ["valid_observation", "masked_but_finite", "missing", "valid_observation"]
    v = valid_only(disp, rm)
    assert np.isnan(v[1]) and v[0] == 1.0 and v[3] == 4.0
    assert issue_state(disp, rm)[1] == MASKED
    rec = from_observation(c[1], "OPERA_S1_ASC", disp[1], "2024-07-01", "2024-07-13")
    assert rec["status"] == "sensor_limit" and rec["value"] is None
    with pytest.raises(ValueError):
        record("sensor_limit", "OPERA_S1_ASC", "LOS_DISPLACEMENT_MM", value=2.0)
    # filter: a masked value passed as NaN must give the same result as never seeing it
    y, td = _series()
    y2 = y.copy(); y2[30, 0] = 1e6                                  # a wild masked value...
    o_nan = run_filter(np.where(np.arange(len(td))[:, None] == 30, np.nan, y), td, SSConfig())
    o_masked = run_filter(valid_only(y2, np.where(np.arange(len(td))[:, None] == 30, 0, 1)), td, SSConfig())
    assert np.allclose(o_nan["level"], o_masked["level"], equal_nan=True)


# 2
def test_f18904_catalog_footprint_and_orbit_verified_or_blocked():
    p = V3 / "_cmr_F18904_raw.json"
    if not p.exists():
        pytest.skip("BLOCKED: CMR record for F18904 not saved (run Phase 0 catalog query)")
    recs = json.load(open(p))
    assert len(recs) > 0
    attrs = [{a["Name"]: a["Values"][0] for a in r["AdditionalAttributes"]} for r in recs]
    assert {a["ASCENDING_DESCENDING"] for a in attrs} == {"DESCENDING"}
    assert {a["PATH_NUMBER"] for a in attrs} == {"71"} and {a["FRAME_NUMBER"] for a in attrs} == {"18904"}
    sub = sorted((ROOT / "data/raw/opera_F18904").glob("*.nc"))
    if not sub:
        pytest.skip("catalog verified (DESCENDING, track 71); AOI subset not on disk yet -> grid check BLOCKED")
    import xarray as xr
    a = xr.open_dataset(sub[0]); b = xr.open_dataset(ROOT / "data/processed/opera_F16940_stack.nc")
    assert_same_grid(a.x.values, a.y.values, b.x.values, b.y.values)
    assert np.isfinite(a.displacement.values).mean() > 0.9


# 3
def test_no_future_observation_in_filter_or_forecast():
    y, td = _series()
    o1 = run_filter(y, td, SSConfig(huber_c=2.5, cp_nis=9, cp_vel_var=1e-3))
    y2 = y.copy(); y2[41:] = np.random.default_rng(5).normal(0, 50, y2[41:].shape)
    o2 = run_filter(y2, td, SSConfig(huber_c=2.5, cp_nis=9, cp_vel_var=1e-3))
    for k in ("level", "vel", "var_vel", "cov_lv"):
        assert np.array_equal(o1[k][:41], o2[k][:41], equal_nan=True)
    k = np.full(5, 40); p = np.arange(5)
    f1 = forecast_increment(o1, k, p, np.full(5, 12.0), y[40], SSConfig())
    f2 = forecast_increment(o2, k, p, np.full(5, 12.0), y2[40], SSConfig())
    assert np.allclose(f1[0], f2[0]) and np.allclose(f1[1], f2[1])


# 4
def test_irregular_time_deltas_in_state_transition():
    y, td = _series(T=200, P=200, v=-0.05, R=1.0)
    o = run_filter(y, td, SSConfig(R0=1.0, q=1e-8))
    assert abs(np.nanmean(o["vel"][-1]) + 0.05) < 0.003
    # prediction variance must grow with the real gap: identical history, longer gap -> larger var
    tdA = np.array([0, 12, 24, 36.0]); tdB = np.array([0, 12, 24, 96.0])
    yy = np.array([[0.0], [1.0], [2.0], [np.nan]])
    vA = run_filter(yy, tdA, SSConfig())["var_level"][-1, 0]; vB = run_filter(yy, tdB, SSConfig())["var_level"][-1, 0]
    assert vB > vA
    with pytest.raises(ValueError):
        run_filter(yy, np.array([0, 12, 12, 24.0]), SSConfig())


# 5
def test_phase_to_mm_and_look_vector_sign_using_synthetic_vectors():
    lam = 0.24196
    assert np.isclose(phase_to_los_mm(4 * np.pi, lam, 1), lam * 1000)          # one fringe pair = lambda
    with pytest.raises(TypeError):
        phase_to_los_mm(1.0, lam)                                                 # no default sign
    with pytest.raises(PermissionError):
        signed_los_mm(1.0, lam)                                                   # NISAR sign unverified -> blocked
    assert SIGN_STATUS == "unverified"
    up = np.array([0, 0, 10.0])
    assert project(up, ASC) > 0 and project(up, DESC) > 0                          # uplift is toward both satellites
    east = np.array([10.0, 0, 0])
    assert project(east, ASC) < 0 < project(east, DESC)                            # asc sat is west, desc sat is east
    check_unit(ASC[:, None]); check_unit(DESC[:, None])
    with pytest.raises(GeometryError):
        check_unit(np.array([[0.6], [0.0], [0.6]]))
    l = los_from_xy(0.62, 0.167); assert np.isclose(np.linalg.norm(l), 1) and l[2] > 0


# 6
def test_asc_desc_two_LOS_rank_two_and_3D_unidentifiable():
    r = identifiability(np.array([ASC, DESC]))
    assert r["rank"] == 2 and not r["observable_3d"]
    n = np.array(r["null_space"][0])
    assert abs(n[1]) > 0.95                                                        # unobservable direction ~ north
    u = np.array([-3.0, -20.0, -8.0])
    A = np.array([ASC, DESC])
    assert np.allclose(A @ u, A @ (u + 37.0 * n))                                  # different 3D motion, same data


# 7
def test_zero_north_violation_changes_inferred_east_up():
    A = np.array([ASC, DESC])
    u = np.array([-5.0, -40.0, -10.0])
    d = (A @ u)[:, None]
    s = eu_zero_north(d, A, np.full((2, 1), 1.0))
    lk = north_leakage(A)
    assert np.isclose(s["E"][0] - u[0], lk[0] * u[1]) and np.isclose(s["U"][0] - u[2], lk[1] * u[1])
    assert abs(s["U"][0] - u[2]) > 5.0                                             # 40 mm south -> >5 mm Up bias
    assert s["label"] == "conditional_EU_estimate"
    with pytest.raises(ValueError):
        record("inferred", "FUSION", "CONDITIONAL_EAST_UP", 1.0, 0.5)              # no assumption -> refused


# 8
def test_resampling_keeps_categorical_masks_categorical():
    sx = np.arange(0, 300, 30.0) + 15; sy = np.arange(300, 0, -30.0) - 15
    lab = np.random.default_rng(0).choice([0, 1, 2, 3], (len(sy), len(sx)))
    dx = np.arange(0, 300, 80.0) + 40; dy = np.arange(300, 0, -80.0) - 40
    out = categorical_to_grid(lab, sx, sy, dx, dy)
    assert set(np.unique(out)) <= {0, 1, 2, 3} and out.dtype == lab.dtype
    val = np.ones_like(lab, float); val[0, 0] = 1000.0
    ok = np.ones_like(lab, bool); ok[0, 0] = False                                 # invalid pixel must not leak
    m, frac, n = block_to_grid(val, ok, sx, sy, dx, dy, 80.0, min_valid_frac=0.0)
    assert np.nanmax(m) == 1.0 and frac[0, 0] < 1.0


# 9
def test_nisar_2026_not_used_as_2024_label_or_feature():
    nisar_first = "2025-11-23"
    for issue in pd.date_range("2016-07-19", "2024-12-31", freq="90D"):
        assert not admissible_at(issue, nisar_first)
    assert admissible_at("2026-10-15", "2026-09-20")
    from displacement_forecast.v2common import BASE, STATIC_NAMES
    assert not any("nisar" in f.lower() for f in BASE + STATIC_NAMES)
    src = (Path(__file__).resolve().parents[1] / "state_space_deformation.py").read_text()
    assert "nisar" not in src.split('"""', 2)[2].lower()                           # no NISAR in the SS experiment code


# 10
def test_cross_sensor_interval_reference_and_geometry_alignment():
    s1 = pd.to_datetime(["2025-11-23", "2025-12-05", "2025-12-17", "2025-12-29"])
    m = match_intervals(s1, [("2025-11-23", "2025-12-05"), ("2025-11-24", "2025-12-06"), ("2025-11-20", "2025-12-29")], tol_days=1)
    assert len(m) == 2 and m[0][0] == pd.Timestamp("2025-11-23")
    with pytest.raises(SensorComparisonError):
        check_sensor_comparison({"same_los_geometry_or_projected": True, "sign_convention_verified": False, "units_verified": True},
                                ("2025-11-23", "2025-12-05"), ("2025-11-23", "2025-12-05"))
    with pytest.raises(SensorComparisonError):
        check_sensor_comparison({k: True for k in ("same_los_geometry_or_projected", "sign_convention_verified", "units_verified")},
                                ("2024-07-01", "2024-07-13"), ("2026-09-20", "2026-10-14"))
    t = lambda s: pd.Timestamp(s)
    disp = {t("2025-12-05"): 1.0, t("2025-12-17"): 3.0, t("2025-12-29"): 0.5}
    ref = {t("2025-12-05"): t("2025-09-18"), t("2025-12-17"): t("2025-09-18"), t("2025-12-29"): t("2025-12-17")}
    assert interval_from_ministack(disp, ref, "2025-12-05", "2025-12-17") == 2.0
    assert interval_from_ministack(disp, ref, "2025-12-05", "2025-12-29") == 0.5 + 3.0 - 1.0
    assert interval_from_ministack(disp, ref, "2025-12-05", "2026-01-10") is None


# 11
def test_no_double_ionosphere_troposphere_correction():
    ph = np.ones((3, 3)); io = np.full((3, 3), 0.25)
    out, done = apply_phase_corrections(ph, {"ionosphere": io}, {"ionosphere": "not_applied"})
    assert np.allclose(out, 0.75) and done == ["ionosphere"]
    with pytest.raises(DoubleCorrectionError):
        apply_phase_corrections(out, {"ionosphere": io}, {"ionosphere": "not_applied"}, already=tuple(done))
    with pytest.raises(DoubleCorrectionError):
        apply_phase_corrections(ph, {"wet_troposphere": io}, {"wet_troposphere": "applied"})
    with pytest.raises(DoubleCorrectionError):
        apply_phase_corrections(ph, {"hydrostatic_troposphere": io}, {})
    p = V3 / "nisar_corrections.csv"
    if p.exists():
        c = pd.read_csv(p)
        assert set(c.applied_to_unwrappedPhase) == {"not_applied"}
        assert c.geolocation_flag_meaning.fillna("n/a").str.contains("geolocation|n/a").all()


# 12
def test_no_valid_observation_returns_no_value_and_expanded_uncertainty():
    y, td = _series(T=40, P=1)
    y[20:35] = np.nan
    o = run_filter(y, td, SSConfig())
    vv = o["var_level"][19:35, 0]
    assert np.all(np.diff(vv) > 0)                                                  # uncertainty keeps growing
    assert np.isnan(o["R_used"][25, 0]) and np.isnan(o["nis"][25, 0])               # no update on missing dates
    st = issue_state(np.array([np.nan, 3.0]), np.array([0, 0]))
    recs = [from_observation("missing" if s == "missing" else "masked_but_finite", "OPERA_S1_DESC", 3.0, None, None) for s in st]
    assert all(r["value"] is None and r["status"] == "sensor_limit" for r in recs)


# 13
def test_existing_B0_benchmark_unchanged():
    h = V3 / "benchmark_hashes.json"
    if not h.exists() or not (ROOT / "src").exists():
        pytest.skip("source-repo layout (src/precursor, results_v2) not present in this port; hashes cannot be checked")
    rec = json.load(open(h))["sha256"]
    for f, sha in rec.items():
        assert hashlib.sha256((ROOT / f).read_bytes()).hexdigest() == sha, f"{f} changed"
    exp = pd.read_csv(ROOT / "results_v2/baseline_reproduction.csv")
    assert abs(float(exp.loc[exp.model.str.startswith("B0"), "test_MAE_all"].iloc[0]) - 2.4514) < 1e-3
    ab = V3 / "state_space_ablation.csv"
    if ab.exists():
        a = pd.read_csv(ab)
        assert abs(a.loc[a.family == "A", "test_MAE_all"].iloc[0] - 2.4514) < 1e-3


# 14
def test_strong_motion_future_labels_not_used_for_gating():
    import inspect
    for fn in (run_filter, forecast_increment):
        sig = inspect.signature(fn).parameters
        assert not any(k in sig for k in ("label", "labels", "y_future", "strong"))
    y, td = _series()
    o = run_filter(y, td, SSConfig(cp_nis=9, cp_vel_var=1e-3))
    k = np.full(5, 30); p = np.arange(5)
    a = forecast_increment(o, k, p, np.full(5, 12.0), y[30], SSConfig())
    y_lab = y.copy(); y_lab[31] += 100                                              # the future label is not an input
    assert np.allclose(a[0], forecast_increment(run_filter(y_lab, td, SSConfig(cp_nis=9, cp_vel_var=1e-3)), k, p, np.full(5, 12.0), y_lab[30], SSConfig())[0])


# 15
def test_uncertainty_coverage_uses_identical_valid_pixel_date_cohorts():
    p = V3 / "state_space_intervals.csv"
    if not p.exists():
        pytest.skip("BLOCKED: run scripts/v3_05_state_space.py first")
    iv = pd.read_csv(p)
    ss = iv[iv.method.isin(["raw model SD", "2023-scaled SD"])]
    assert (ss.test_fraction_with_interval == 1.0).all()                            # every matched test sample scored
    a = pd.read_csv(V3 / "state_space_ablation.csv")
    assert a.test_n.nunique() == 1 and a.val_n.nunique() == 1                       # all rows on one sample set
    assert int(a.test_n.iloc[0]) == 304375 and int(a.val_n.iloc[0]) == 133434        # = v2 B0 cohort
