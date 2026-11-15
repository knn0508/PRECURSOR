"""Phase 6 tests. All data are SYNTHETIC or hand-made; passing says nothing about real data."""
import math
import uuid
from datetime import UTC, date, datetime

import numpy as np
import pytest

from app.core.config import Settings, get_settings
from app.main import app
from app.services.features_cv.types import forbidden_names
from app.services.timeseries import adapters, indicators as ind
from app.services.timeseries.analyze import analyze
from app.services.timeseries.forecast import ForecastRequest, Forecaster, NotImplementedForecaster
from app.services.timeseries.lead_features import rainfall_before, value_at_lead
from app.services.timeseries.limitations import limitations
from app.services.timeseries.store import list_series, read_series, write_series
from app.services.timeseries.synthetic import synthetic_los_series, synthetic_rainfall
from app.services.timeseries.types import MixedGeometryError, SeriesPoint, ShortSeriesError, TimeSeries, TimeSeriesError

AREA = uuid.uuid4()
IRREGULAR_DAYS = [0, 12, 24, 36, 60, 72, 84, 108, 120, 144, 156, 180, 192, 216, 240, 252, 276, 300, 312, 336]


# ---------------- known-trend recovery ----------------
def test_noiseless_trend_recovered_exactly_on_irregular_times():
    s = synthetic_los_series(IRREGULAR_DAYS, slope_mm_yr=10.0)
    t, y = s.valid()
    for fn in (ind.linear_trend, ind.theil_sen):
        r = fn(t, y)
        assert r["slope_per_year"] == pytest.approx(10.0, abs=1e-9)
    assert ind.linear_trend(t, y)["intercept"] == pytest.approx(0.0, abs=1e-9)


def test_noisy_trend_recovered_within_stated_tolerance():
    """Tolerance: the true slope (10 mm/yr) lies inside the 95% CI and within 3 standard errors, for 20 seeds, at most 2 CI misses allowed."""
    misses = 0
    for seed in range(20):
        t, y = synthetic_los_series(IRREGULAR_DAYS, slope_mm_yr=10.0, noise_mm=0.5, seed=seed).valid()
        r = ind.linear_trend(t, y)
        assert abs(r["slope_per_year"] - 10.0) < 3 * r["slope_stderr_per_year"]
        lo, hi = r["slope_ci_per_year"]
        misses += not (lo <= 10.0 <= hi)
        lo, hi = ind.theil_sen(t, y)["slope_ci_per_year"]
        assert lo < 10.0 + 3 and hi > 10.0 - 3
    assert misses <= 2


def test_theil_sen_is_robust_to_an_outlier_where_ols_is_not():
    t, y = synthetic_los_series(IRREGULAR_DAYS, slope_mm_yr=10.0).valid()
    y = y.copy()
    y[-1] += 500.0
    assert abs(ind.theil_sen(t, y)["slope_per_year"] - 10.0) < 1.0
    assert abs(ind.linear_trend(t, y)["slope_per_year"] - 10.0) > 20.0


def test_velocity_change_between_windows():
    t = np.arange(0, 400, 20.0)
    y = np.where(t < 200, 5.0 * t / 365.25, 5.0 * 200 / 365.25 + 15.0 * (t - 200) / 365.25)
    r = ind.velocity_change(t, y, split_day=200.0)
    assert r["slope_first_per_year"] == pytest.approx(5.0, abs=1e-9) and r["slope_second_per_year"] == pytest.approx(15.0, abs=1e-9)
    assert r["change_per_year"] == pytest.approx(10.0, abs=1e-9)
    with pytest.raises(ShortSeriesError):
        ind.velocity_change(t, y, split_day=60.0)  # first window has 3 points < 5


def test_acceleration_recovered_and_requires_n():
    days = [0, 20, 45, 60, 90, 110, 150, 170, 200, 240]
    t, y = synthetic_los_series(days, slope_mm_yr=3.0, quad_mm_yr2=8.0).valid()
    r = ind.acceleration(t, y)
    assert r["acceleration_per_year2"] == pytest.approx(8.0, abs=1e-6)
    assert r["minimum_n"] == 8
    with pytest.raises(ShortSeriesError, match="at least 8"):
        ind.acceleration(t[:7], y[:7])


# ---------------- Mann-Kendall (hand computed) ----------------
def test_mann_kendall_hand_values():
    y = np.arange(1.0, 11.0)  # strictly increasing, n = 10: S = 45, Var = 10*9*25/18 = 125, Z = (45-1)/sqrt(125)
    r = ind.mann_kendall(y)
    assert r["s"] == 45 and r["variance_s"] == pytest.approx(125.0) and r["z"] == pytest.approx(44 / math.sqrt(125))
    assert r["trend"] == "increasing"
    s, var = ind.mk_statistics(np.array([1.0, 2.0, 2.0, 3.0]))  # one tie group of 2: S = 5, Var = (4*3*13 - 2*1*9)/18
    assert s == 5 and var == pytest.approx((156 - 18) / 18)
    assert ind.mann_kendall(-y)["trend"] == "decreasing"
    assert ind.mann_kendall(np.array([1.0, 3, 2, 4, 3, 2, 4, 3, 2, 3]))["trend"] == "no_monotonic_trend_detected"
    assert ind.mann_kendall(np.ones(10))["trend"] == "NOT_AVAILABLE"


# ---------------- short series, gaps, irregular sampling ----------------
def test_short_series_refused_everywhere():
    t, y = np.arange(4.0), np.arange(4.0)
    for fn in (ind.linear_trend, ind.theil_sen):
        with pytest.raises(ShortSeriesError, match="at least 5"):
            fn(t, y)
    with pytest.raises(ShortSeriesError, match="at least 10"):
        ind.mann_kendall(np.arange(9.0))
    res = analyze(synthetic_los_series([0, 12, 24], slope_mm_yr=1.0))
    assert all(v["status"] == "NOT_AVAILABLE" for v in res["indicators"].values())


def test_gaps_reported_not_filled():
    s = synthetic_los_series(IRREGULAR_DAYS, slope_mm_yr=10.0, nan_at=(5, 6, 7))
    rep = limitations(s, gap_factor=2.0)
    assert rep["n_points"] == 20 and rep["n_valid"] == 17 and rep["missing_fraction"] == pytest.approx(3 / 20)
    assert rep["gaps"] and rep["gaps"][0]["interval_days"] == 60.0  # valid days 60 -> 120 around the three NaNs
    assert [p.value is None for p in s.points].count(True) == 3  # nothing interpolated
    t, y = s.valid()
    assert len(t) == 17 and ind.linear_trend(t, y)["slope_per_year"] == pytest.approx(10.0, abs=1e-9)  # actual times used, gaps untouched


def test_limitations_stats_and_aliasing():
    s = synthetic_los_series([0, 12, 24, 36, 48, 60], slope_mm_yr=1.0)
    rep = limitations(s, min_period_days=20.0)
    assert rep["median_interval_days"] == 12.0 and rep["span_days"] == 60.0 and rep["interval_cv"] == 0.0
    assert rep["aliasing"] == "POSSIBLE"  # 2 * 12 = 24 > 20
    assert limitations(s, min_period_days=24.0)["aliasing"] == "NOT_INDICATED"
    assert limitations(s)["aliasing"] == "NOT_ASSESSED"
    one = limitations(synthetic_los_series([0], slope_mm_yr=1.0))
    assert one["median_interval_days"] is None


# ---------------- guards ----------------
def _pt(day, **kw):
    base = dict(time=datetime(2026, 1, 1 + day, tzinfo=UTC), value=1.0, source="S", sensor="NISAR", synthetic=True, track=5, orbit_direction="ASCENDING", look_direction="RIGHT")
    return SeriesPoint(**{**base, **kw})


def test_mixed_geometry_refused():
    with pytest.raises(MixedGeometryError):
        TimeSeries("los_velocity_mm_yr", "z", [_pt(0), _pt(1, orbit_direction="DESCENDING")])
    with pytest.raises(MixedGeometryError):
        TimeSeries("los_velocity_mm_yr", "z", [_pt(0), _pt(1, track=6)])
    with pytest.raises(MixedGeometryError):
        TimeSeries("los_velocity_mm_yr", "z", [_pt(0), _pt(1, sensor="Sentinel-1")])
    with pytest.raises(MixedGeometryError):
        TimeSeries("los_velocity_mm_yr", "z", [_pt(0, orbit_direction=None), _pt(1, orbit_direction=None)])  # geometry unknown
    TimeSeries("los_velocity_mm_yr", "z", [_pt(0), _pt(1)])  # consistent: fine


def test_chronology_and_timezone_enforced():
    with pytest.raises(TimeSeriesError, match="chronological"):
        TimeSeries("los_velocity_mm_yr", "z", [_pt(1), _pt(0)])
    with pytest.raises(TimeSeriesError, match="chronological"):
        TimeSeries("los_velocity_mm_yr", "z", [_pt(0), _pt(0)])
    with pytest.raises(TimeSeriesError, match="timezone"):
        TimeSeries("rainfall_mm_day", "z", [_pt(0, time=datetime(2026, 1, 1))])
    with pytest.raises(TimeSeriesError, match="unknown series kind"):
        TimeSeries("risk_score", "z", [_pt(0)])
    assert TimeSeries("rainfall_mm_day", "z", [_pt(0, value=float("nan"))]).points[0].value is None  # NaN normalised to missing


# ---------------- rainfall indices (hand computed) ----------------
def test_antecedent_sums_hand_values_and_missing_days():
    p = np.array([1.0, 2, 3, 4, 5, 6, 7])
    s = ind.antecedent_sums(p, (1, 3))
    assert s[1].tolist() == [1, 2, 3, 4, 5, 6, 7] and np.isnan(s[3][:2]).all() and s[3][2:].tolist() == [6, 9, 12, 15, 18]
    q = p.copy()
    q[3] = np.nan
    s2 = ind.antecedent_sums(q, (3,))[3]
    assert np.isnan(s2[3:6]).all() and s2[2] == 6 and s2[6] == 18  # a window touching the gap is NaN, never a partial sum


def test_api_recurrence_hand_values_and_missing_propagation():
    assert ind.antecedent_precipitation_index(np.array([2.0, 0.0, 4.0]), 0.5, spinup_days=0).tolist() == [2.0, 1.0, 4.5]
    a = ind.antecedent_precipitation_index(np.array([1.0, 1, np.nan, 1, 1, 1]), 0.5, spinup_days=1)
    assert np.isnan(a[[0, 2, 3]]).all() and a[1] == pytest.approx(1.5) and a[4] == pytest.approx(1.5) and a[5] == pytest.approx(1.75)  # state restarts after the gap
    assert ind.antecedent_precipitation_index(np.ones(50), 0.5)[-1] == pytest.approx(2.0, abs=1e-6)
    with pytest.raises(TimeSeriesError):
        ind.antecedent_precipitation_index(np.ones(5), 1.0)


def test_storm_events_hand_values():
    r = ind.storm_events(np.array([0, 2, 3, 0, 0, 5, np.nan, 4.0]), date(2026, 1, 1), 1.0)
    assert r["n_events"] == 3 and r["missing_days"] == 1 and r["peak_mm_day"] == 5.0
    e0, e1, e2 = r["events"]
    assert (e0["start"], e0["end"], e0["duration_days"], e0["total_mm"], e0["peak_mm_day"]) == ("2026-01-02", "2026-01-03", 2, 5.0, 3.0)
    assert e1["adjacent_to_missing_day"] and e2["adjacent_to_missing_day"] and not e0["adjacent_to_missing_day"]
    assert "not an alert" in r["caveat"]


def test_lagged_correlation_descriptive_and_refusals():
    rng = np.random.default_rng(3)
    x = rng.random(60)
    days = np.arange(60)
    y = np.full(60, np.nan)
    y[3:] = x[:-3]  # y(d) = x(d - 3): correlation peaks at lag +3
    res = ind.lagged_correlation(days, x, days, y, [0, 3])
    by = {r["lag_days"]: r for r in res["lags"]}
    assert by[3]["pearson_r"] == pytest.approx(1.0) and by[3]["n_pairs"] == 57 and abs(by[0]["pearson_r"]) < 0.5
    assert "not causation" in res["caveat"]
    few = ind.lagged_correlation(days[:5], x[:5], days[:5], x[:5], [0])
    assert few["lags"][0]["status"] == "NOT_AVAILABLE"
    const = ind.lagged_correlation(days, np.ones(60), days, x, [0])
    assert const["lags"][0]["reason"] == "constant series"


# ---------------- lead-time building blocks ----------------
def test_lead_time_values():
    s = synthetic_rainfall([1.0, 2, 3, 4, 5, None, 7, 8])  # Jan 1 .. Jan 8, Jan 6 missing
    assert rainfall_before(s, date(2026, 1, 8), 1) == 7.0  # reference day itself excluded
    assert math.isnan(rainfall_before(s, date(2026, 1, 8), 2))  # Jan 6 missing: never a partial sum
    assert rainfall_before(s, date(2026, 1, 6), 3) == 5.0 + 4.0 + 3.0
    assert math.isnan(rainfall_before(s, date(2026, 1, 2), 3))  # window starts before the series
    assert value_at_lead(s, date(2026, 1, 8), 1, max_age_days=2) == 7.0
    assert math.isnan(value_at_lead(s, date(2026, 1, 1), 1, max_age_days=2))  # nothing before the series


# ---------------- forecaster interface ----------------
def test_forecaster_is_not_implemented():
    f = NotImplementedForecaster()
    assert isinstance(f, Forecaster)
    r = f.forecast(None, ForecastRequest(kind="los_displacement_mm", zone="z", horizon_days=30))
    assert r.status == "NOT_IMPLEMENTED" and r.values is None and r.uncertainty is None


# ---------------- adapters, store, API ----------------
def test_adapters():
    recs = [{"date": "2026-01-01", "precip_mm_day": 1.5, "observed": True}, {"date": "2026-01-02", "precip_mm_day": None, "observed": False}]
    s = adapters.from_rainfall_daily(recs, "z", source="GPM IMERG", sensor="IMERG", synthetic=True)
    assert [p.value for p in s.points] == [1.5, None] and s.points[0].time == datetime(2026, 1, 1, tzinfo=UTC)
    pairs = [{"reference_time": "2026-01-13T00:00:00+00:00", "secondary_time": "2026-01-25T00:00:00+00:00", "mean_velocity_mm_yr": 4.0, "orbit_direction": "ASCENDING", "track": 7, "look_direction": "RIGHT"},
             {"reference_time": "2026-01-01T00:00:00+00:00", "secondary_time": "2026-01-13T00:00:00+00:00", "mean_velocity_mm_yr": 3.0, "orbit_direction": "ASCENDING", "track": 7, "look_direction": "RIGHT"}]
    v = adapters.from_insar_pair_velocities(pairs, "z", source="NISAR GUNW", sensor="NISAR", synthetic=True)
    assert [p.value for p in v.points] == [3.0, 4.0] and v.points[0].time == datetime(2026, 1, 7, tzinfo=UTC) and "not independent" in v.notes[0]
    pairs[0]["orbit_direction"] = "DESCENDING"
    with pytest.raises(MixedGeometryError):
        adapters.from_insar_pair_velocities(pairs, "z", source="NISAR GUNW", sensor="NISAR", synthetic=True)


def test_store_roundtrip_and_name_safety(tmp_path):
    s = synthetic_los_series(IRREGULAR_DAYS, slope_mm_yr=2.0, nan_at=(3,))
    write_series(tmp_path, AREA, s)
    back = read_series(tmp_path, AREA, "synthetic-zone", "los_displacement_mm")
    assert [(p.time, p.value) for p in back.points] == [(p.time, p.value) for p in s.points]
    assert list_series(tmp_path, AREA)[0]["contains_synthetic_data"] is True
    for bad in ("../x", "a/b", ""):
        with pytest.raises(TimeSeriesError):
            read_series(tmp_path, AREA, bad, "los_displacement_mm")
    with pytest.raises(FileNotFoundError):
        read_series(tmp_path, AREA, "nope", "coherence")
    assert list_series(tmp_path, uuid.uuid4()) == []


def test_api(plain_client, tmp_path):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, data_root=tmp_path)
    try:
        write_series(tmp_path, AREA, synthetic_los_series(IRREGULAR_DAYS, slope_mm_yr=10.0))
        r = plain_client.get(f"/api/v1/timeseries/areas/{AREA}/series")
        assert r.status_code == 200 and r.json()["series"][0]["kind"] == "los_displacement_mm"
        a = plain_client.get(f"/api/v1/timeseries/areas/{AREA}/series/synthetic-zone/los_displacement_mm/analysis").json()
        assert a["indicators"]["linear_trend"]["slope_per_year"] == pytest.approx(10.0, abs=1e-9)
        assert a["real_data_validation"] == "NOT_PERFORMED" and a["contains_synthetic_data"] is True
        assert plain_client.get(f"/api/v1/timeseries/areas/{AREA}/series/none/coherence/analysis").status_code == 404
        assert plain_client.get(f"/api/v1/timeseries/areas/{AREA}/series/synthetic-zone/risk/analysis").status_code == 422
        assert plain_client.get(f"/api/v1/timeseries/areas/{AREA}/series/synthetic-zone/los_displacement_mm/analysis?alpha=2").status_code == 422
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_rainfall_analysis_and_boundary():
    s = synthetic_rainfall([0, 2, 3, 0, 0, 5, 0] + [1.0] * 60)  # 67 days > the 44-day spin-up for k = 0.9
    a = analyze(s, api_k=0.9)
    assert a["rainfall"]["antecedent_sums_last_value"]["7"] == 7.0 and a["rainfall"]["storm_events"]["n_events"] >= 2 and a["rainfall"]["api_last_value"] is not None
    gap = analyze(synthetic_rainfall([1.0, 2.0]))
    assert gap["indicators"]["linear_trend"]["status"] == "NOT_AVAILABLE"

    def keys(o, acc):
        if isinstance(o, dict):
            for k, v in o.items():
                acc.add(k)
                keys(v, acc)
        elif isinstance(o, list):
            for v in o:
                keys(v, acc)
        return acc
    assert not forbidden_names(keys(a, set()))  # no score-like / risk-like names anywhere in the output
    assert "forecast" not in " ".join(keys(a, set())).lower()
