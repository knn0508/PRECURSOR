"""Half-hourly rainfall tests. ALL fixtures are SYNTHETIC (rainfall/synthetic_half_hourly.py); passing them is NOT
real-data validation. Constant field value r mm/hr over 48 intervals = r x 0.5 x 48 mm per UTC day."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest
from shapely.geometry import box

from app.services.environmental.features.rainfall_features import rainfall_features
from app.services.environmental.rainfall import reader as rd
from app.services.environmental.rainfall.half_hourly import HalfHourlyFile, process_rainfall_half_hourly
from app.services.environmental.rainfall.precipitation_processor import RainfallFile, process_rainfall
from app.services.environmental.rainfall.synthetic import write_corrupt_file, write_synthetic_imerg
from app.services.environmental.rainfall.synthetic_half_hourly import write_synthetic_half_hour
from app.services.environmental.types import DataOrigin, EnvError, LayerStatus, MeasurementKind, NotAvailable

AOI = box(116.1, 4.1, 116.3, 4.3)
UTC = timezone.utc


def day_files(tmp_path, d, rate=2.0, skip=(), acq=True, tag=""):
    out = []
    for k in range(48):
        if k in skip:
            continue
        t = datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(minutes=30 * k)
        p = write_synthetic_half_hour(tmp_path / f"hh{tag}_{d}_{k:02d}.h5", t, rate)
        out.append(HalfHourlyFile(t, p, f"acq-{d}-{k}" if acq else None))
    return out


def run(files, start, end, **kw):
    return process_rainfall_half_hourly(files, AOI, start, end, **kw)


def test_full_day_exact_accumulation(tmp_path):
    d = date(2024, 3, 10)
    r = run(day_files(tmp_path, d), d, d)
    assert r.daily[0]["precip_mm_day"] == pytest.approx(48.0) and r.daily[0]["observed"]  # 2 mm/hr x 0.5 h x 48
    assert r.daily[0]["intervals_observed"] == 48 and r.daily[0]["intervals_expected"] == 48
    assert r.status == LayerStatus.PROCESSED and r.counts["partial_days"] == 0


def test_varying_rates_hand_computed(tmp_path):
    d = date(2024, 3, 10)
    files = []
    for k in range(48):
        t = datetime(2024, 3, 10, tzinfo=UTC) + timedelta(minutes=30 * k)
        files.append(HalfHourlyFile(t, write_synthetic_half_hour(tmp_path / f"v{k}.h5", t, float(k))))
    # sum_k k x 0.5 = 0.5 x 1128 = 564
    assert run(files, d, d).daily[0]["precip_mm_day"] == pytest.approx(564.0)


def test_one_missing_interval_day_not_observed_never_zero(tmp_path):
    d = date(2024, 3, 10)
    r = run(day_files(tmp_path, d, skip=(7,)), d, d)
    row = r.daily[0]
    assert row["precip_mm_day"] is None and row["observed"] is False and row["intervals_observed"] == 47
    assert r.counts["partial_days"] == 1 and r.counts["observed_days"] == 0
    assert any("partial day" in w for w in r.warnings) and r.status == LayerStatus.PARTIALLY_PROCESSED


def test_zero_interval_day_is_missing_and_not_partial(tmp_path):
    d1, d2 = date(2024, 3, 10), date(2024, 3, 11)
    r = run(day_files(tmp_path, d1), d1, d2)
    assert r.daily[1]["precip_mm_day"] is None and r.daily[1]["intervals_observed"] == 0
    assert r.counts["partial_days"] == 0 and r.counts["missing_days"] == 1


def test_leap_day_and_month_boundary(tmp_path):
    s, e = date(2024, 2, 28), date(2024, 3, 1)
    files = [f for i in range(3) for f in day_files(tmp_path, s + timedelta(days=i), rate=1.0, tag="L")]
    r = run(files, s, e, windows=(3,))
    assert [x["date"] for x in r.daily] == ["2024-02-28", "2024-02-29", "2024-03-01"]
    assert all(x["precip_mm_day"] == pytest.approx(24.0) for x in r.daily)
    assert r.rolling[2]["sum_3d_mm"] == pytest.approx(72.0) and r.rolling[1]["sum_3d_mm"] is None
    assert all(not m["complete"] and m["sum_mm"] is None for m in r.monthly)  # partial months stay null


def test_full_month_sum_uses_complete_month_rule(tmp_path):
    s, e = date(2024, 2, 1), date(2024, 2, 29)
    # reuse one set of files per day cheaply: 29 days x 48 files
    files = [f for i in range(29) for f in day_files(tmp_path, s + timedelta(days=i), rate=1.0, tag="M")]
    r = run(files, s, e)
    assert r.monthly[0]["complete"] and r.monthly[0]["sum_mm"] == pytest.approx(29 * 24.0)


def test_interval_with_all_aoi_cells_fill_counts_missing(tmp_path):
    d = date(2024, 3, 10)
    files = day_files(tmp_path, d, skip=(5,))
    t = datetime(2024, 3, 10, 2, 30, tzinfo=UTC)
    p = write_synthetic_half_hour(tmp_path / "fill.h5", t, 2.0, fill_block=(slice(0, 20), slice(0, 24)))
    r = run(files + [HalfHourlyFile(t, p, "a")], d, d)
    assert r.daily[0]["precip_mm_day"] is None and r.daily[0]["intervals_observed"] == 47


def test_duplicate_timestamp_identical_and_conflicting(tmp_path):
    d = date(2024, 3, 10)
    files = day_files(tmp_path, d)
    t0 = files[0].start_time
    same = HalfHourlyFile(t0, write_synthetic_half_hour(tmp_path / "dup.h5", t0, 2.0), "x")
    r = run(files + [same], d, d)
    assert r.daily[0]["precip_mm_day"] == pytest.approx(48.0) and any("duplicate interval" in w for w in r.warnings)
    diff = HalfHourlyFile(t0, write_synthetic_half_hour(tmp_path / "dup2.h5", t0, 3.0), "y")
    with pytest.raises(EnvError, match="duplicate interval"):
        run(files + [diff], d, d)


def test_off_grid_and_outside_window_ignored_with_warning(tmp_path):
    d = date(2024, 3, 10)
    files = day_files(tmp_path, d)
    t = datetime(2024, 3, 10, 0, 15, tzinfo=UTC)
    off = HalfHourlyFile(t, write_synthetic_half_hour(tmp_path / "off.h5", t, 9.0))
    t2 = datetime(2024, 3, 12, tzinfo=UTC)
    out = HalfHourlyFile(t2, write_synthetic_half_hour(tmp_path / "out.h5", t2, 9.0))
    r = run(files + [off, out], d, d)
    assert r.daily[0]["precip_mm_day"] == pytest.approx(48.0)
    assert any("30-minute grid" in w for w in r.warnings) and any("outside window" in w for w in r.warnings)


def test_naive_start_time_rejected(tmp_path):
    f = HalfHourlyFile(datetime(2024, 3, 10), tmp_path / "x.h5")
    with pytest.raises(EnvError):
        run([f], date(2024, 3, 10), date(2024, 3, 10))


def test_units_rules(tmp_path):
    d = date(2024, 3, 10)
    t = datetime(2024, 3, 10, tzinfo=UTC)
    bad = HalfHourlyFile(t, write_synthetic_half_hour(tmp_path / "day.h5", t, 2.0, units="mm/day"))
    with pytest.raises(NotAvailable):  # only file, refused -> nothing usable
        run([bad], d, d)
    r = run([bad] + day_files(tmp_path, d)[1:], d, d)
    assert r.file_errors and "not mm/hr" in r.file_errors[0]["error"]
    t1 = datetime(2024, 3, 10, 0, 30, tzinfo=UTC)
    nou = HalfHourlyFile(t1, write_synthetic_half_hour(tmp_path / "nou.h5", t1, 2.0, units=None))
    r2 = run([nou], d, d)
    assert any("mm/hr is ASSUMED" in w for w in r2.warnings)


def test_rate_file_refused_as_daily_and_daily_refused_as_rate(tmp_path):
    t = datetime(2024, 3, 10, tzinfo=UTC)
    p = write_synthetic_half_hour(tmp_path / "rate.h5", t, 2.0)
    with pytest.raises(EnvError, match="not mm/day"):
        rd.read_daily_aoi(p, AOI, t.date())  # a rate is never a daily accumulation
    q = write_synthetic_imerg(tmp_path / "daily.nc4", t.date(), np.full((20, 24), 2.0))
    with pytest.raises(EnvError, match="not mm/hr"):
        rd.read_daily_aoi(q, AOI, t.date(), expected_units="rate")


def test_corrupt_file_tolerated(tmp_path):
    d = date(2024, 3, 10)
    t = datetime(2024, 3, 10, tzinfo=UTC)
    bad = HalfHourlyFile(t, write_corrupt_file(tmp_path / "bad.h5"))
    r = run([bad] + day_files(tmp_path, d)[1:], d, d)
    assert len(r.file_errors) == 1 and r.status == LayerStatus.PARTIALLY_PROCESSED
    assert r.daily[0]["intervals_observed"] == 47 and r.daily[0]["precip_mm_day"] is None


def test_nothing_usable_raises(tmp_path):
    t = datetime(2024, 3, 10, tzinfo=UTC)
    with pytest.raises(NotAvailable):
        run([HalfHourlyFile(t, write_corrupt_file(tmp_path / "bad.h5"))], date(2024, 3, 10), date(2024, 3, 10))


def test_provenance_origin(tmp_path):
    d = date(2024, 3, 10)
    r = run(day_files(tmp_path, d), d, d)
    assert r.provenance_daily.measurement_kind == MeasurementKind.DERIVED_MEASUREMENT
    assert r.provenance_daily.origin == DataOrigin.SYNTHETIC_FIXTURE and r.provenance_daily.dataset_name == "GPM_3IMERGHH"
    assert any("SYNTHETIC" in w for w in r.warnings)


def test_hash_stable_and_differs_from_daily(tmp_path):
    d = date(2024, 3, 10)
    files = day_files(tmp_path, d)
    a, b = run(files, d, d).input_hash, run(list(reversed(files)), d, d).input_hash
    assert a == b
    dp = write_synthetic_imerg(tmp_path / "d.nc4", d, np.full((20, 24), 1.0))
    assert process_rainfall([RainfallFile(d, dp, "a")], AOI, d, d).input_hash != a


def test_features_json_and_shape_compat(tmp_path):
    d = date(2024, 3, 10)
    r = run(day_files(tmp_path, d), d, d)
    f = rainfall_features(r)
    assert f["features"]["total_mm_over_observed_days"]["value"] == pytest.approx(48.0)
    json.dumps(r.to_dict())
    dp = write_synthetic_imerg(tmp_path / "d.nc4", d, np.full((20, 24), 1.0), units="mm/day")
    daily_keys = set(process_rainfall([RainfallFile(d, dp, "a")], AOI, d, d).to_dict())
    assert set(r.to_dict()) == daily_keys
