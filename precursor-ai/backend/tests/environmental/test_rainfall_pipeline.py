"""Rainfall tests. ALL fixtures are SYNTHETIC IMERG-like files (see rainfall/synthetic.py); passing them is NOT
real-data validation. Grid: 20 lat x 24 lon cells, centres lat 4.05+0.1i, lon 116.05+0.1j; field[i, j] = 10*i + j unless noted."""
from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pytest
from shapely.geometry import box

from app.services.environmental.features.rainfall_features import rainfall_features
from app.services.environmental.rainfall import reader as rd
from app.services.environmental.rainfall import temporal_aggregation as ta
from app.services.environmental.rainfall.precipitation_processor import RainfallFile, process_rainfall
from app.services.environmental.rainfall.synthetic import default_grid, write_corrupt_file, write_synthetic_imerg
from app.services.environmental.types import DataOrigin, EnvError, LayerStatus, MeasurementKind, NotAvailable

AOI4 = box(116.1, 4.1, 116.3, 4.3)  # centres of cells (1,1),(1,2),(2,1),(2,2) -> 11,12,21,22
LAT, LON = default_grid()
FIELD = (10 * np.arange(20)[:, None] + np.arange(24)[None, :]).astype(float)


def mk(tmp_path, day, field=FIELD, name=None, **kw):
    return write_synthetic_imerg(tmp_path / (name or f"imerg_{day}.nc4"), day, field, **kw)


def const_files(tmp_path, days, v=1.0):
    return [RainfallFile(d, mk(tmp_path, d, np.full((20, 24), v)), f"acq-{d}") for d in days]


def drange(a, n):
    return [a + timedelta(days=i) for i in range(n)]


# ---- reader / AOI statistic -------------------------------------------------------------------------------
@pytest.mark.parametrize("layout", ["time_lon_lat", "time_lat_lon", "lat_lon"])
@pytest.mark.parametrize("desc", [False, True])
def test_aoi_mean_exact_all_layouts(tmp_path, layout, desc):
    r = rd.read_daily_aoi(mk(tmp_path, date(2024, 1, 1), layout=layout, lat_descending=desc), AOI4)
    assert r.stat.mean_mm_day == pytest.approx(16.5) and (r.stat.min_mm_day, r.stat.max_mm_day) == (11, 22)
    assert r.stat.n_cells == r.stat.n_valid == 4 and r.stat.method == "cell_centres_in_aoi"
    assert r.synthetic and r.variable_path == "/Grid/precipitation" and r.date == date(2024, 1, 1)


def test_centre_in_polygon_excludes_cell_whose_centre_is_outside(tmp_path):
    # edge cuts through cells but only centres (116.15, 4.15) and (116.25, 4.15)... box x 116.1-116.3, y 4.1-4.2
    r = rd.read_daily_aoi(mk(tmp_path, date(2024, 1, 1)), box(116.1, 4.1, 116.3, 4.2))
    assert r.stat.n_cells == 2 and r.stat.mean_mm_day == pytest.approx(11.5)


def test_fill_block_is_nan_not_zero(tmp_path):
    r = rd.read_daily_aoi(mk(tmp_path, date(2024, 1, 1), fill_block=(slice(1, 2), slice(1, 2))), AOI4)
    assert r.stat.n_valid == 3 and r.stat.mean_mm_day == pytest.approx((12 + 21 + 22) / 3)
    assert r.fill_value == pytest.approx(-9999.9, rel=1e-6)


def test_all_fill_gives_none_not_zero(tmp_path):
    r = rd.read_daily_aoi(mk(tmp_path, date(2024, 1, 1), fill_block=(slice(0, 20), slice(0, 24))), AOI4)
    assert r.stat.mean_mm_day is None and r.stat.n_valid == 0


def test_tiny_aoi_uses_centroid_cell_with_warning(tmp_path):
    r = rd.read_daily_aoi(mk(tmp_path, date(2024, 1, 1)), box(116.16, 4.16, 116.18, 4.18))
    assert r.stat.method == "centroid_cell" and r.stat.mean_mm_day == 11 and r.stat.n_cells == 1
    assert any("not local rainfall" in w for w in r.warnings)


def test_outside_grid_not_available(tmp_path):
    with pytest.raises(NotAvailable):
        rd.read_daily_aoi(mk(tmp_path, date(2024, 1, 1)), box(100.0, 1.0, 100.2, 1.2))


def test_unit_mismatch_refused_and_missing_units_warned(tmp_path):
    with pytest.raises(EnvError, match="not mm/day"):
        rd.read_daily_aoi(mk(tmp_path, date(2024, 1, 1), units="mm/hr"), AOI4)
    r = rd.read_daily_aoi(mk(tmp_path, date(2024, 1, 2), units=None), AOI4)
    assert not r.units_verified and any("ASSUMED" in w for w in r.warnings)


def test_missing_variable_reports_what_was_found(tmp_path):
    with pytest.raises(EnvError, match="precipitation variable not found"):
        rd.read_daily_aoi(mk(tmp_path, date(2024, 1, 1), var_name="randomError"), AOI4)


def test_date_from_file_and_mismatch(tmp_path):
    p = mk(tmp_path, date(2024, 5, 6))
    assert rd.read_daily_aoi(p, AOI4).date == date(2024, 5, 6)
    with pytest.raises(EnvError, match="declared date"):
        rd.read_daily_aoi(p, AOI4, date(2024, 5, 7))


def test_normalize_units():
    assert rd.normalize_units("mm/day") == "daily" and rd.normalize_units("mm/hr") == "rate"
    assert rd.normalize_units(None) == "unknown" and rd.normalize_units("kg m-2") == "other"


# ---- temporal aggregation ---------------------------------------------------------------------------------
def test_missing_days_are_nan_never_zero():
    df, _ = ta.build_daily_series([(date(2024, 1, 1), 2.0), (date(2024, 1, 3), 4.0)], date(2024, 1, 1), date(2024, 1, 4))
    assert df["precip_mm_day"].isna().tolist() == [False, True, False, True]
    assert df["observed"].tolist() == [True, False, True, False]
    c = ta.summary_counts(df)
    assert (c["observed_days"], c["missing_days"]) == (2, 2)
    assert c["missing_ranges"] == [{"start": "2024-01-02", "end": "2024-01-02", "days": 1},
                                   {"start": "2024-01-04", "end": "2024-01-04", "days": 1}]
    assert (c["first_observed"], c["last_observed"]) == ("2024-01-01", "2024-01-03")


def test_monthly_needs_every_day_and_leap_february():
    d = date(2024, 2, 1)
    df, _ = ta.build_daily_series([(x, 1.0) for x in drange(d, 29)], d, date(2024, 2, 29))
    m = ta.monthly_accumulation(df)
    assert m.loc["2024-02", "sum_mm"] == 29.0 and m.loc["2024-02", "expected_days"] == 29
    df2, _ = ta.build_daily_series([(x, 1.0) for x in drange(d, 28)], d, date(2024, 2, 29))  # 29th missing
    m2 = ta.monthly_accumulation(df2)
    assert np.isnan(m2.loc["2024-02", "sum_mm"]) and m2.loc["2024-02", "observed_days"] == 28
    # non-leap February has 28 expected days
    df3, _ = ta.build_daily_series([(x, 1.0) for x in drange(date(2023, 2, 1), 28)], date(2023, 2, 1), date(2023, 2, 28))
    assert ta.monthly_accumulation(df3).loc["2023-02", "sum_mm"] == 28.0


def test_month_boundary_partial_window_is_incomplete():
    s, e = date(2024, 1, 31), date(2024, 2, 2)  # fully observed window, but months are only partly covered
    df, _ = ta.build_daily_series([(x, 1.0) for x in drange(s, 3)], s, e)
    m = ta.monthly_accumulation(df)
    assert m["complete"].tolist() == [False, False] and m["sum_mm"].isna().all()
    assert m["expected_days"].tolist() == [31, 29] and m["observed_days"].tolist() == [1, 2]


def test_rolling_windows_need_complete_window():
    s = date(2024, 1, 1)
    obs = [(x, float(i + 1)) for i, x in enumerate(drange(s, 10)) if i != 4]  # day 5 missing
    df, _ = ta.build_daily_series(obs, s, date(2024, 1, 10))
    r = ta.rolling_accumulation(df, (3, 7))
    assert np.isnan(r["sum_3d_mm"].iloc[0:2]).all()
    assert r["sum_3d_mm"].iloc[2] == 6.0  # 1+2+3
    assert np.isnan(r["sum_3d_mm"].iloc[4:7]).all()  # windows containing the gap
    assert r["sum_3d_mm"].iloc[7] == 21.0  # days 6+7+8 are all observed
    assert np.isnan(r["sum_7d_mm"].iloc[:10]).all()  # every 7-day window up to day 10 contains day 5


def test_duplicates_rule():
    a, b = date(2024, 1, 1), date(2024, 1, 2)
    df, w = ta.build_daily_series([(a, 1.0), (a, 1.0)], a, b)
    assert any("duplicate" in x for x in w) and df["precip_mm_day"].iloc[0] == 1.0
    with pytest.raises(EnvError, match="duplicate"):
        ta.build_daily_series([(a, 1.0), (a, 2.0)], a, b)


def test_out_of_window_ignored_and_bad_range():
    df, w = ta.build_daily_series([(date(2023, 1, 1), 5.0)], date(2024, 1, 1), date(2024, 1, 2))
    assert df["observed"].sum() == 0 and any("outside" in x for x in w)
    with pytest.raises(EnvError):
        ta.build_daily_series([], date(2024, 1, 2), date(2024, 1, 1))


def test_rate_vs_accumulation_conversion():
    assert ta.rate_to_accumulation_mm(2.0, 0.5) == 1.0  # 2 mm/hr for a half hour = 1 mm
    assert ta.rate_to_accumulation_mm(np.full(48, 2.0), 0.5).sum() == pytest.approx(48.0)  # 48 steps = 1 day at 2 mm/hr
    with pytest.raises(EnvError):
        ta.rate_to_accumulation_mm(1.0, 0)


# ---- processor --------------------------------------------------------------------------------------------
def test_process_full_month_leap_feb(tmp_path):
    days = drange(date(2024, 2, 1), 29)
    res = process_rainfall(const_files(tmp_path, days, 2.0), AOI4, date(2024, 2, 1), date(2024, 2, 29))
    assert res.status == LayerStatus.PROCESSED and res.counts["missing_days"] == 0
    assert res.monthly[0]["sum_mm"] == pytest.approx(58.0) and res.monthly[0]["complete"]
    assert res.rolling[-1]["sum_30d_mm"] is None and res.rolling[-1]["sum_7d_mm"] == pytest.approx(14.0)
    assert res.provenance_daily.measurement_kind == MeasurementKind.SOURCE_OBSERVATION
    assert res.provenance_accumulations.measurement_kind == MeasurementKind.DERIVED_MEASUREMENT
    assert res.provenance_daily.origin == DataOrigin.SYNTHETIC_FIXTURE and res.provenance_daily.units == "mm/day"
    assert res.provenance_accumulations.units == "mm" and res.provenance_daily.provider == "GPM"
    assert all("/" not in n and "\\" not in n for n in res.provenance_daily.source_files)
    assert res.quality.valid_percent == 100.0 and res.quality.aoi_coverage_percent == 100.0


def test_process_missing_and_corrupt_and_outside(tmp_path):
    days = drange(date(2024, 3, 1), 6)
    files = const_files(tmp_path, [days[0], days[1], days[3]], 1.0)
    files.append(RainfallFile(days[4], write_corrupt_file(tmp_path / "bad.nc4"), None))
    files.append(RainfallFile(date(2023, 1, 1), tmp_path / "x.nc4", None))
    res = process_rainfall(files, AOI4, days[0], days[5], windows=(3,))
    assert res.status == LayerStatus.PARTIALLY_PROCESSED
    assert res.counts["observed_days"] == 3 and res.counts["missing_days"] == 3
    assert [e["file"] for e in res.file_errors] == ["bad.nc4"]
    assert any("outside window" in w for w in res.warnings)
    assert [d["precip_mm_day"] for d in res.daily] == [1.0, 1.0, None, 1.0, None, None]
    assert all(r["sum_3d_mm"] is None for r in res.rolling)  # no complete 3-day window
    assert res.monthly[0]["sum_mm"] is None
    f = rainfall_features(res)["features"]
    assert f["total_mm_over_observed_days"]["value"] == 3.0 and "OBSERVED" in f["total_mm_over_observed_days"]["note"]
    assert f["last_complete_3d_sum"]["value"] is None and f["max_daily_mm"]["value"] == 1.0
    assert f["monthly_totals_complete_months"]["value"] == {}


def test_features_last_complete_windows(tmp_path):
    days = drange(date(2024, 1, 1), 8)
    res = process_rainfall(const_files(tmp_path, days, 3.0), AOI4, days[0], days[-1])
    f = rainfall_features(res)["features"]
    assert f["last_complete_3d_sum"]["value"] == 9.0 and f["last_complete_7d_sum"]["value"] == 21.0
    assert f["last_complete_30d_sum"]["value"] is None
    assert f["observed_days"]["value"] == 8 and f["temporal_coverage_percent"]["value"] == 100.0


def test_no_usable_file_not_available(tmp_path):
    bad = RainfallFile(date(2024, 1, 1), write_corrupt_file(tmp_path / "bad.nc4"), None)
    with pytest.raises(NotAvailable):
        process_rainfall([bad], AOI4, date(2024, 1, 1), date(2024, 1, 3))
    with pytest.raises(NotAvailable):
        process_rainfall([], AOI4, date(2024, 1, 1), date(2024, 1, 3))


def test_unit_mismatch_file_is_per_file_error(tmp_path):
    good = const_files(tmp_path, [date(2024, 1, 1)])
    badf = RainfallFile(date(2024, 1, 2), mk(tmp_path, date(2024, 1, 2), units="mm/hr"), None)
    res = process_rainfall(good + [badf], AOI4, date(2024, 1, 1), date(2024, 1, 2))
    assert res.counts["observed_days"] == 1 and "not mm/day" in res.file_errors[0]["error"]


def test_duplicate_file_dates_conflicting_raises(tmp_path):
    d = date(2024, 1, 1)
    a = RainfallFile(d, mk(tmp_path, d, np.full((20, 24), 1.0), name="a.nc4"), None)
    b = RainfallFile(d, mk(tmp_path, d, np.full((20, 24), 2.0), name="b.nc4"), None)
    with pytest.raises(EnvError, match="duplicate"):
        process_rainfall([a, b], AOI4, d, d)


def test_input_hash_stable_and_sensitive(tmp_path):
    days = drange(date(2024, 1, 1), 3)
    files = const_files(tmp_path, days)
    h = process_rainfall(files, AOI4, days[0], days[-1]).input_hash
    assert h == process_rainfall(list(reversed(files)), AOI4, days[0], days[-1]).input_hash
    assert h != process_rainfall(files, AOI4, days[0], days[-1], windows=(2,)).input_hash
    assert h != process_rainfall(files, AOI4, days[0], days[-1] + timedelta(days=1)).input_hash
    assert h != process_rainfall(files, box(116.1, 4.1, 116.2, 4.2), days[0], days[-1]).input_hash
    assert h != process_rainfall(files[:2], AOI4, days[0], days[-1]).input_hash


def test_json_serialisable(tmp_path):
    days = drange(date(2024, 1, 1), 4)
    res = process_rainfall(const_files(tmp_path, days)[:3], AOI4, days[0], days[-1])
    s = json.dumps(res.to_dict())
    assert "NaN" not in s and str(tmp_path) not in s
    json.dumps(rainfall_features(res))


def test_square_grid_without_dimension_scales_is_refused(tmp_path):
    """SYNTHETIC: equal lat/lon length and no dimension scales -> axis order ambiguous, refused (not guessed)."""
    lat, lon = default_grid(10, 10)
    p = write_synthetic_imerg(tmp_path / "sq.nc4", date(2024, 1, 1), np.ones((10, 10)), lat=lat, lon=lon)
    with pytest.raises(EnvError, match="ambiguous"):
        rd.read_daily_aoi(p, box(116.1, 4.1, 116.3, 4.3))
