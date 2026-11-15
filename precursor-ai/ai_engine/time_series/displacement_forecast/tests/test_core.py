"""Unit tests on small synthetic arrays (pipeline mechanics only; not scientific results)."""
import numpy as np
import pandas as pd
import torch

from displacement_forecast import models as M
from displacement_forecast.dataset import (build_samples, chronological_split, crossing_labels,
                               crossing_threshold, rain_features, target_index, Scaler)
from displacement_forecast.train import baseline_predictions


def _stack(T=40, H=6, W=6, rate=0.5, seed=0):
    rng = np.random.default_rng(seed)
    times = pd.date_range("2020-01-01", periods=T, freq="12D")
    t = np.arange(T, dtype=np.float32) * 12
    cum = (rate * t)[:, None, None] + rng.normal(0, 0.1, (T, H, W)).astype(np.float32)
    valid = np.ones_like(cum, bool)
    coh = np.full_like(cum, 0.9)
    static = np.zeros((2, H, W), np.float32)
    return cum, valid, coh, times, static


def test_causal_tcn_future_does_not_affect_past():
    torch.manual_seed(0)
    tcn = M.TCN(4, 8, 3, (1, 2, 4, 8), dropout=0.0).eval()
    x = torch.randn(2, 10, 4)
    y1 = tcn(x)
    x2 = x.clone(); x2[:, 6:] = torch.randn(2, 4, 4) * 100
    y2 = tcn(x2)
    assert torch.allclose(y1[:, :6], y2[:, :6], atol=1e-5)
    assert not torch.allclose(y1[:, 6:], y2[:, 6:])


def test_lstm_tcn_causal_end_to_end():
    m = M.build("lstm_tcn", 6, 5, 3).eval()
    x, s = torch.randn(3, 6, 5), torch.randn(3, 3)
    q, _ = m(x, s)
    assert q.shape == (3, 3)
    assert torch.all(q[:, 0] <= q[:, 1]) and torch.all(q[:, 1] <= q[:, 2])  # ordered quantiles


def test_increment_units_and_horizon():
    cum, valid, coh, times, static = _stack(rate=0.5)
    ss = build_samples(cum, valid, coh, times, static, ["a", "b"], window=6, horizon=12, tol=3, pixel_stride=1)
    assert np.allclose(ss.h_days, 12)
    assert abs(np.median(ss.y) - 6.0) < 0.5            # 0.5 mm/day * 12 days
    fi = ss.feat_names.index("dt_days")
    assert np.allclose(ss.X[..., fi], 12)


def test_irregular_dates_never_relabelled():
    times = pd.DatetimeIndex(pd.to_datetime(["2020-01-01", "2020-01-07", "2020-01-25", "2020-02-20"]))
    idx = target_index(times, 12, 3)
    assert idx[0] == -1  # +6 and +24 days are outside 12±3: no target, not a fake "12-day" one
    assert idx[1] == -1  # +18 days
    assert idx[2] == -1  # +26 days


def test_no_future_leakage_in_features():
    cum, valid, coh, times, static = _stack()
    a = build_samples(cum, valid, coh, times, static, ["a", "b"], window=6, pixel_stride=1)
    k_cut = 20
    cum2 = cum.copy(); cum2[k_cut + 2:] += 1000.0     # perturb everything after the issue+target of k_cut
    b = build_samples(cum2, valid, coh, times, static, ["a", "b"], window=6, pixel_stride=1)
    sel_a = a.issue_time <= times.values[k_cut]
    sel_b = b.issue_time <= times.values[k_cut]
    assert np.array_equal(a.X[sel_a], b.X[sel_b])


def test_rain_features_are_past_only():
    times = pd.date_range("2020-01-01", periods=5, freq="12D")
    rain = pd.Series(1.0, index=pd.date_range("2019-11-01", "2020-03-31", freq="D"))
    base = rain_features(times, rain)
    rain2 = rain.copy(); rain2[rain2.index > times[2]] = 500.0
    pert = rain_features(times, rain2)
    assert np.allclose(base[:3], pert[:3], equal_nan=True)
    assert np.allclose(base[1:, 0], 12.0)


def test_split_embargo_and_train_only_threshold():
    cum, valid, coh, times, static = _stack(T=80)
    ss = build_samples(cum, valid, coh, times, static, ["a", "b"], window=6, pixel_stride=1)
    sp = chronological_split(ss, "2021-06-01", "2022-01-01")
    tr, va, te = (ss.subset(sp[k]) for k in ("train", "val", "test"))
    assert tr.target_time.max() < np.datetime64("2021-06-01")
    assert va.issue_time.min() >= np.datetime64("2021-06-01") and va.target_time.max() < np.datetime64("2022-01-01")
    assert te.issue_time.min() >= np.datetime64("2022-01-01")
    th = crossing_threshold(tr)
    ss2 = ss.subset(np.arange(len(ss))); ss2.y = ss2.y.copy()
    ss2.y[sp["test"]] *= 100                           # changing test targets must not move tau
    assert crossing_threshold(ss2.subset(sp["train"]))["tau_mm_day"] == th["tau_mm_day"]
    sc = Scaler().fit(tr)
    assert np.isfinite(sc.xs).all()


def test_crossing_label_definition():
    cum, valid, coh, times, static = _stack()
    ss = build_samples(cum, valid, coh, times, static, ["a", "b"], window=6, pixel_stride=1)
    ss.last_vel[:] = 0.1
    ss.y[:] = 0.0; ss.y[:5] = 12 * 2.0                  # 2 mm/day over 12 days
    lab = crossing_labels(ss, tau=1.0)
    assert lab[:5].sum() == 5 and lab[5:].sum() == 0
    ss.last_vel[:5] = 3.0                               # already above tau => not an onset
    assert crossing_labels(ss, tau=1.0).sum() == 0


def test_baselines_constant_velocity():
    cum, valid, coh, times, static = _stack(rate=0.5)
    ss = build_samples(cum, valid, coh, times, static, ["a", "b"], window=6, pixel_stride=1)
    b = baseline_predictions(ss)
    assert abs(np.median(b["constant_velocity_window"]) - 6.0) < 0.5
    assert np.all(b["zero_motion"] == 0)


def test_dilations_cover_window_without_excess():
    for T in (3, 6, 12, 24):
        d = M.dilations_for(T)
        assert M.receptive_field(3, d) >= T
        assert len(d) == 1 or M.receptive_field(3, d[:-1]) < T   # minimal
    assert M.dilations_for(6) == (1, 2)


def test_scaler_ignores_unobserved_steps():
    cum, valid, coh, times, static = _stack(T=40, rate=0.5)
    valid[10:14, :3] = False                 # gaps -> zero-filled placeholders in X
    ss = build_samples(cum, valid, coh, times, static, ["a", "b"], window=6, min_valid_steps=4, pixel_stride=1)
    sc = Scaler().fit(ss)
    i = ss.feat_names.index("inc_mm")
    obs = ss.X[..., ss.feat_names.index("valid")] > 0
    assert np.isclose(sc.xm[i], ss.X[..., i][obs].mean(), atol=1e-4)


def test_common_mode_removes_per_date_offset_without_touching_local_motion():
    import xarray as xr
    from displacement_forecast.opera import remove_common_mode
    rng = np.random.default_rng(1)
    T, H, W = 60, 20, 20
    times = pd.date_range("2020-01-01", periods=T, freq="12D")
    t = np.arange(T) * 12.0
    motion = np.zeros((T, H, W)); motion[:, :5, :5] = (-0.3 * t)[:, None, None]   # landslide corner
    atmo = rng.normal(0, 15, T)[:, None, None]                                     # same shift for all pixels
    cum = (motion + atmo + rng.normal(0, 0.5, (T, H, W))).astype(np.float32)
    st = xr.Dataset({"cum_mm": (("time", "y", "x"), cum), "valid": (("time", "y", "x"), np.ones_like(cum, bool)),
                     "coherence": (("time", "y", "x"), np.ones_like(cum))}, coords={"time": times})
    out, rep = remove_common_mode(st, str(times[40].date()), min_train_obs=10, min_pixels=10)
    c = out.cum_mm.values
    assert not out.stable_mask.values[:5, :5].any()                    # moving area never used as reference
    assert np.std(c[:, 10:, 10:].mean((1, 2))) < 1.0                   # stable area ~flat after correction
    slope = np.polyfit(t, c[:, :5, :5].mean((1, 2)), 1)[0]
    assert abs(slope + 0.3) < 0.02                                     # local motion preserved


def test_thin_to_cadence_keeps_reference_dates_and_12_day_spacing():
    from displacement_forecast.opera import thin_to_cadence
    sec = pd.date_range("2020-01-01", periods=40, freq="6D")
    ref = [sec[0] - pd.Timedelta(days=6) if i < 20 else sec[19] for i in range(40)]   # ministack switch at sec[19]
    man = pd.DataFrame({"granule_id": [f"g{i}" for i in range(40)], "secondary_dt": sec, "reference_dt": ref})
    out = thin_to_cadence(man)
    kept = pd.to_datetime(out.secondary_dt)
    assert sec[19] in set(kept)                                    # reference date retained -> chaining works
    gaps = kept.diff().dt.days.dropna()
    assert (gaps >= 6).all() and gaps.median() == 12
    assert len(out) < len(man)


def test_neighbourhood_features_are_causal_per_date():
    from displacement_forecast.spatial import neighbourhood_features
    rng = np.random.default_rng(3)
    cum = rng.normal(0, 1, (20, 15, 15)).astype(np.float32).cumsum(0)
    valid = np.ones_like(cum, bool)
    a = neighbourhood_features(cum, valid)
    cum2 = cum.copy(); cum2[12:] += rng.normal(0, 50, (8, 15, 15))       # change the future only
    b = neighbourhood_features(cum2, valid)
    for k in a:
        assert np.allclose(np.nan_to_num(a[k][:12]), np.nan_to_num(b[k][:12]))   # dates < 12 unaffected


def test_local_inc_removes_uniform_shift():
    from displacement_forecast.spatial import neighbourhood_features
    T, H, W = 10, 20, 20
    cum = np.zeros((T, H, W), np.float32)
    cum += (np.arange(T) * 7.0)[:, None, None]                           # same shift everywhere (atmosphere-like)
    cum[:, 10, 10] += np.arange(T) * 2.0                                  # local motion at one pixel
    f = neighbourhood_features(cum, np.ones_like(cum, bool))
    assert np.allclose(f["local_inc"][1:, 10, 10], 2.0, atol=1e-4)
    assert np.allclose(f["local_inc"][1:, 3, 3], 0.0, atol=1e-4)


def test_patch_gather_matches_numpy():
    from displacement_forecast.spatial import PatchSource
    rng = np.random.default_rng(0)
    g = rng.normal(size=(12, 3, 10, 11)).astype(np.float32)
    src = PatchSource(g, window=4, patch=5, device="cpu")
    k, r, c = torch.tensor([5, 11]), torch.tensor([0, 7]), torch.tensor([3, 10])
    out = src.gather(k, r, c).numpy()
    gp = np.pad(g, ((0, 0), (0, 0), (2, 2), (2, 2)))
    for b in range(2):
        ref = gp[k[b] - 3:k[b] + 1, :, r[b]:r[b] + 5, c[b]:c[b] + 5]
        assert np.allclose(out[b], ref)
        assert np.allclose(out[b][-1, :, 2, 2], g[k[b], :, r[b], c[b]])   # centre = the pixel itself, last step = issue date


def test_elevation_tropo_removes_stratified_delay_and_keeps_trend():
    import xarray as xr
    from displacement_forecast.opera import remove_elevation_tropo
    rng = np.random.default_rng(5)
    T, H, W = 80, 30, 30
    times = pd.date_range("2018-01-01", periods=T, freq="12D")
    elev = np.tile(np.linspace(0, 400, W), (H, 1))
    t = np.arange(T) * 12.0
    tropo = rng.normal(0, 0.03, T)[:, None, None] * (elev - np.median(elev))[None]   # random per date, ~12 mm per 400 m
    motion = np.zeros((T, H, W)); motion[:, :6, :6] = (-0.1 * t)[:, None, None]        # landslide at low elevation
    cum = (motion + tropo + rng.normal(0, 0.5, (T, H, W))).astype(np.float32)
    stable = np.ones((H, W), bool); stable[:8, :8] = False
    st = xr.Dataset({"cum_mm": (("time", "y", "x"), cum), "valid": (("time", "y", "x"), np.ones_like(cum, bool)),
                     "stable_mask": (("y", "x"), stable)}, coords={"time": times})
    out, rep = remove_elevation_tropo(st, elev, str(times[50].date()))
    c = out.cum_mm.values
    before = np.std(np.diff(cum, axis=0)[:, stable]); after = np.std(np.diff(c, axis=0)[:, stable])
    assert after < 0.5 * before                                              # stratified delay removed
    slope = np.polyfit(t, c[:, :6, :6].mean((1, 2)), 1)[0]
    assert abs(slope + 0.1) < 0.01                                           # landslide trend preserved


def test_quality_classes_never_turn_missing_into_zero_motion():
    from displacement_forecast import quality_audit as QA
    disp = np.array([[0.0, np.nan], [5.0, -3.0]], np.float32)
    rec = np.array([[1, 1], [0, 1]], np.float32)
    cls = QA.classify(disp, rec)
    assert cls[0, 1] == QA.ABSENT                     # NaN stays absent even where the mask says good
    assert cls[0, 0] == QA.OBSERVED                   # a real 0.0 measurement stays observed
    assert cls[1, 0] == QA.MASKED_FINITE and cls[1, 1] == QA.OBSERVED
    code = QA.reason_codes(cls, cc=np.array([[1, 1], [0, 1]]), tc=np.array([[.9, .9], [.4, .9]]))
    assert code[1, 0] == (QA.R_CC0 | QA.R_LOW_TC) and code[0, 0] == 0


def test_invalid_target_is_dropped_not_zero_labelled():
    cum, valid, coh, times, static = _stack(T=30, rate=0.5)
    valid[20, 2, 2] = False
    ss = build_samples(cum, valid, coh, times, static, ["a", "b"], window=6, min_valid_steps=4, pixel_stride=1)
    tgt = pd.DatetimeIndex(ss.target_time)
    bad = (ss.pix[:, 0] == 2) & (ss.pix[:, 1] == 2) & (tgt == times[20])
    assert not bad.any()                              # no sample whose label date is unobserved
    assert np.all(np.isfinite(ss.y))


def test_temporal_features_causal_and_correct():
    from displacement_forecast.temporal_features import window_trend, time_since_valid, build_temporal_features
    T, H, W = 40, 3, 3
    times = pd.date_range("2020-01-01", periods=T, freq="12D")
    t = np.arange(T) * 12.0
    cum = np.broadcast_to((0.25 * t)[:, None, None], (T, H, W)).astype(np.float32).copy()
    valid = np.ones((T, H, W), bool)
    w = window_trend(cum, valid, times, 144.0, 6)
    assert np.allclose(w["vel"][20:], 0.25, atol=1e-5)          # exact line -> exact slope
    assert np.allclose(w["resid"][20:], 0.0, atol=1e-4)          # no deviation from the trend
    a = build_temporal_features(cum, valid, times)
    cum2 = cum.copy(); cum2[25:] += 100.0                        # change only the future
    b = build_temporal_features(cum2, valid, times)
    for k in a:
        assert np.allclose(np.nan_to_num(a[k][:25]), np.nan_to_num(b[k][:25])), k
    v = valid.copy(); v[10:15, 0, 0] = False
    ts = time_since_valid(v, times)
    assert ts[14, 0, 0] == 5 * 12 and ts[15, 0, 0] == 0 and ts[14, 1, 1] == 0


def test_residual_flags_noise_on_current_date():
    from displacement_forecast.temporal_features import window_trend
    T = 30
    times = pd.date_range("2020-01-01", periods=T, freq="12D")
    cum = (np.arange(T) * 12.0 * 0.1)[:, None, None].astype(np.float32).repeat(2, 1).repeat(2, 2)
    cum[20] += 8.0                                               # a noisy current point
    w = window_trend(cum, np.ones_like(cum, bool), times, 144.0, 6)
    assert w["resid"][20, 0, 0] > 5.0                            # deviation is visible to the model at t


def test_shuffled_or_duplicated_timestamps_are_rejected():
    import pytest
    cum, valid, coh, times, static = _stack(T=20)
    bad = times.tolist(); bad[5], bad[6] = bad[6], bad[5]
    with pytest.raises(ValueError):
        build_samples(cum, valid, coh, pd.DatetimeIndex(bad), static, ["a", "b"], window=6)
    dup = times.tolist(); dup[7] = dup[6]
    with pytest.raises(ValueError):
        build_samples(cum, valid, coh, pd.DatetimeIndex(dup), static, ["a", "b"], window=6)


def test_labels_are_increments_of_cumulative_not_cumulative_itself():
    cum, valid, coh, times, static = _stack(T=30, rate=0.7, seed=4)
    ss = build_samples(cum, valid, coh, times, static, ["a", "b"], window=6, pixel_stride=1)
    ti = {t: i for i, t in enumerate(times.values)}
    k = np.array([ti[t] for t in ss.issue_time]); m = np.array([ti[t] for t in ss.target_time])
    expect = cum[m, ss.pix[:, 0], ss.pix[:, 1]] - cum[k, ss.pix[:, 0], ss.pix[:, 1]]
    assert np.allclose(ss.y, expect, atol=1e-5)
    assert not np.allclose(ss.y, cum[m, ss.pix[:, 0], ss.pix[:, 1]])        # not the cumulative value
    inc = ss.X[..., ss.feat_names.index("inc_mm")][:, -1]
    expect_inc = cum[k, ss.pix[:, 0], ss.pix[:, 1]] - cum[k - 1, ss.pix[:, 0], ss.pix[:, 1]]
    assert np.allclose(inc, expect_inc, atol=1e-5)                         # inputs are increments too


def test_unit_and_phase_conversions_are_explicit():
    import pytest
    from displacement_forecast.physics_checks import to_mm, phase_to_los_mm
    assert np.allclose(to_mm([0.0125], "meters"), 12.5) and np.allclose(to_mm([3.0], "mm"), 3.0)
    with pytest.raises(ValueError):
        to_mm([1.0], "radians")
    lam = 0.2419632429378531                                               # NISAR L-band, from the GUNW file
    assert np.isclose(phase_to_los_mm(2 * np.pi, lam, +1), lam / 2 * 1000)   # one cycle = lambda/2 of LOS
    assert np.isclose(phase_to_los_mm(1.0, lam, -1), -phase_to_los_mm(1.0, lam, +1))
    with pytest.raises(ValueError):
        phase_to_los_mm(1.0, lam, 0)                                       # no silent default sign


def test_opera_meters_are_scaled_to_mm_in_the_stack(tmp_path):
    import json, xarray as xr
    from displacement_forecast.opera import build_stack
    ds = xr.Dataset({"displacement": (("y", "x"), np.full((2, 2), 0.004, np.float32)),
                     "recommended_mask": (("y", "x"), np.ones((2, 2), np.float32))}, coords={"y": [0, 1], "x": [0, 1]})
    ds.attrs["meta_json"] = json.dumps({"units": {"displacement": "meters"}, "crs_wkt": "EPSG:32611"})
    ds.to_netcdf(tmp_path / "g1.nc", engine="h5netcdf")
    man = pd.DataFrame({"granule_id": ["g1"], "reference_dt": ["2020-01-01"], "secondary_dt": ["2020-01-13"]})
    st = build_stack(man, tmp_path)
    assert np.allclose(st.cum_mm.values[-1], 4.0)                          # 0.004 m -> 4 mm


def test_sensor_comparison_refused_until_verified():
    import pytest
    from displacement_forecast.physics_checks import check_sensor_comparison, SensorComparisonError
    ok = {"same_los_geometry_or_projected": True, "sign_convention_verified": True, "units_verified": True}
    check_sensor_comparison(ok, ("2026-09-20", "2026-10-14"), ("2026-09-22", "2026-10-16"))
    with pytest.raises(SensorComparisonError):
        check_sensor_comparison({**ok, "sign_convention_verified": False}, ("2026-09-20", "2026-10-14"), ("2026-09-20", "2026-10-14"))
    with pytest.raises(SensorComparisonError):                             # OPERA ends 2026-03, NISAR pair is Sep-Oct 2026
        check_sensor_comparison(ok, ("2026-02-27", "2026-03-11"), ("2026-09-20", "2026-10-14"))


def test_quality_classes_partition_and_original_mask_kept():
    from displacement_forecast import quality_mask as QM
    rng = np.random.default_rng(2)
    shp = (5, 4, 4)
    cube = {"recommended_mask": (rng.random(shp) > .3).astype(np.float32),
            "temporal_coherence": rng.random(shp).astype(np.float32),
            "connected_component_labels": (rng.random(shp) > .2).astype(np.float32)}
    finite = rng.random(shp) > .1
    cfg = QM.mask_configs(cube, finite)
    assert np.array_equal(cfg["original"], (cube["recommended_mask"] > .5) & finite)
    for v in cfg.values():
        assert not (v & ~finite).any()                    # no config can validate a missing value
        cls = QM.qa_classes(v, finite)
        assert set(np.unique(cls)) <= {QM.A, QM.B, QM.C}
        assert np.array_equal(cls == QM.C, ~finite)
    assert (cfg["conservative_tc0.8"] <= cfg["conservative_tc0.7"]).all() and (cfg["conservative_tc0.7"] <= cfg["original"]).all()


def test_bilateral_does_not_cross_invalid_boundary_and_keeps_edges():
    from displacement_forecast.spatial import masked_bilateral
    cum = np.zeros((1, 9, 9), np.float32); cum[0, :, 5:] = 100.0          # sharp boundary (landslide edge)
    valid = np.ones_like(cum, bool); valid[0, :, 4] = False               # masked column between the sides
    out = masked_bilateral(cum, valid, sigma_s=1.5, sigma_r=3.0, radius=2)
    assert np.isnan(out[0, :, 4]).all()                                   # invalid stays invalid (no filling)
    assert np.allclose(out[0, :, :4], 0.0, atol=1e-6)                     # left side untouched by the right side
    assert np.allclose(out[0, :, 5:], 100.0, atol=1e-6)
    valid2 = np.ones_like(cum, bool)                                      # even without the hole, the range term
    out2 = masked_bilateral(cum, valid2, sigma_s=1.5, sigma_r=3.0, radius=2)
    assert abs(out2[0, 4, 4]) < 1e-3 and abs(out2[0, 4, 5] - 100) < 1e-3  # keeps the 100 mm step
