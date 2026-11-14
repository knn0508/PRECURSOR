"""Rainfall stage, OPTIONAL half-hourly input: 30-min IMERG-like mm/hr RATE files + AOI -> the same RainfallResult as the
daily pipeline.

Each interval's AOI rate is converted to an accumulation (rate x 0.5 h). A UTC day is OBSERVED only when all 48 intervals
are present and valid; a partial day is NOT observed (null), never scaled up, zero-filled or interpolated. Monthly /
rolling sums reuse temporal_aggregation unchanged. No ML, no forecasts, no thresholds.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

import hashlib
import json
from collections import defaultdict
from datetime import date as Date, datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

from shapely.geometry.base import BaseGeometry

from app.services.environmental.rainfall import reader as rd
from app.services.environmental.rainfall import temporal_aggregation as ta
from app.services.environmental.rainfall.precipitation_processor import ASSUMED_VERSION, RainfallResult  # noqa: F401
from app.services.environmental.types import (
    DataOrigin, EnvError, LayerQuality, LayerStatus, MeasurementKind, NotAvailable, Provenance)

DATASET_NAME = "GPM_3IMERGHH"
STEP_HOURS = 0.5
INTERVALS_PER_DAY = 48


class HalfHourlyFile(NamedTuple):
    start_time: datetime  # UTC-aware start of the 30-minute interval
    path: str | Path
    acquisition_id: str | None = None


def _utc(t: datetime) -> datetime:
    if t.tzinfo is None:
        raise EnvError(f"half-hourly start_time must be timezone-aware (UTC): {t.isoformat()}")
    return t.astimezone(timezone.utc)


def compute_input_hash(files: list[HalfHourlyFile], aoi: BaseGeometry, start: Date, end: Date,
                       windows: tuple[int, ...]) -> str:
    items = []
    for f in sorted(files, key=lambda x: (_utc(x.start_time), Path(x.path).name)):
        p = Path(f.path)
        items.append([_utc(f.start_time).isoformat(), p.name, p.stat().st_size if p.exists() else None, f.acquisition_id])
    payload = {"product": "half_hourly", "files": items, "aoi": aoi.wkt, "start": start.isoformat(),
               "end": end.isoformat(), "windows": sorted(int(w) for w in windows)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def process_rainfall_half_hourly(files: list[HalfHourlyFile], aoi, start: Date, end: Date,
                                 windows: tuple[int, ...] = ta.DEFAULT_WINDOWS) -> RainfallResult:
    warns: list[str] = []
    errors: list[dict[str, str]] = []
    stats: list[dict[str, Any]] = []
    reads: list[rd.DailyAoi] = []
    used: list[HalfHourlyFile] = []
    rate: dict[datetime, float | None] = {}  # interval start -> AOI mean RATE (mm/hr); None = missing interval

    for f in files:
        name = Path(f.path).name
        t = _utc(f.start_time)
        if t.minute % 30 or t.second or t.microsecond:
            warns.append(f"{name}: start time {t.isoformat()} is not on the 30-minute grid: ignored")
            continue
        if t.date() < start or t.date() > end:
            warns.append(f"{name}: interval {t.isoformat()} outside window {start}..{end}: ignored")
            continue
        try:
            r = rd.read_daily_aoi(f.path, aoi, t.date(), expected_units="rate")
        except (EnvError, NotAvailable) as e:
            errors.append({"file": name, "date": t.isoformat(), "error": str(e)})
            continue
        v = r.stat.mean_mm_day  # legacy field name: here it holds the mm/hr RATE
        if t in rate:
            if rate[t] != v:
                raise EnvError(f"duplicate interval {t.isoformat()} with different values ({rate[t]} vs {v})")
            warns.append(f"duplicate interval {t.isoformat()} with identical value: counted once")
            continue
        rate[t] = v
        reads.append(r)
        used.append(f)
        warns += [f"{name}: {w}" for w in r.warnings]
        stats.append({"date": t.isoformat(), "n_cells": r.stat.n_cells, "n_valid": r.stat.n_valid,
                      "min_mm_hr": r.stat.min_mm_day, "max_mm_hr": r.stat.max_mm_day, "method": r.stat.method})

    valid = {t: v for t, v in rate.items() if v is not None}
    if not valid:
        detail = "; ".join(f"{e['file']}: {e['error']}" for e in errors[:3])
        raise NotAvailable("no usable half-hourly rainfall interval for the AOI and window"
                           + (f" ({detail})" if detail else ""))

    per_day: dict[Date, list[float]] = defaultdict(list)
    for t, v in valid.items():
        per_day[t.date()].append(float(ta.rate_to_accumulation_mm(v, STEP_HOURS)))
    obs = [(d, sum(a) if len(a) == INTERVALS_PER_DAY else None) for d, a in per_day.items()]

    daily, w2 = ta.build_daily_series(obs, start, end)
    warns += w2
    monthly = ta.monthly_accumulation(daily)
    rolling = ta.rolling_accumulation(daily, windows)
    counts = ta.summary_counts(daily)
    rec = ta.series_to_records(daily, rolling, monthly)

    detail_days = []
    for row in rec["daily"]:
        n = len(per_day.get(Date.fromisoformat(row["date"]), []))
        row["intervals_observed"], row["intervals_expected"] = n, INTERVALS_PER_DAY
        detail_days.append({"date": row["date"], "intervals_observed": n, "intervals_expected": INTERVALS_PER_DAY})
    partial = [d for d in detail_days if 0 < d["intervals_observed"] < INTERVALS_PER_DAY]
    counts["intervals_expected_per_day"] = INTERVALS_PER_DAY
    counts["partial_days"] = len(partial)
    counts["day_interval_detail"] = detail_days

    if partial:
        warns.append(f"{len(partial)} partial day(s) (<{INTERVALS_PER_DAY} valid intervals): NOT observed, value null; "
                     "missing intervals are never zero-filled, interpolated or scaled up")
    if counts["missing_days"]:
        warns.append(f"{counts['missing_days']} of {counts['expected_days']} days are missing and were NOT filled; "
                     "sums are only reported for fully observed months/windows")
    warns.append("daily value = sum of 48 half-hour accumulations (rate mm/hr x 0.5 h); AOI value is a ~0.1 degree "
                 "cell statistic (satellite estimate); resolution is not increased")

    synthetic = [r.synthetic for r in reads]
    if all(synthetic):
        origin = DataOrigin.SYNTHETIC_FIXTURE
        warns.append("SYNTHETIC test fixture: not real rainfall")
    elif any(synthetic):
        origin = DataOrigin.SYNTHETIC_FIXTURE
        warns.append("input mixes synthetic and non-synthetic files: labelled SYNTHETIC_FIXTURE")
    else:
        origin = DataOrigin.REAL_SATELLITE if all(u.acquisition_id for u in used) else DataOrigin.LOCAL_UNVERIFIED
    versions = {r.dataset_version for r in reads if r.dataset_version}
    version = versions.pop() if len(versions) == 1 else None
    if len(versions) > 1:
        warns.append("files report different product versions")
    names = sorted({Path(u.path).name for u in used})
    acq = sorted({u.acquisition_id for u in used if u.acquisition_id})
    res = reads[0].native_resolution_deg

    def prov(method: str) -> Provenance:
        return Provenance(
            provider="GPM", dataset_name=DATASET_NAME, dataset_version=version, origin=origin,
            measurement_kind=MeasurementKind.DERIVED_MEASUREMENT, acquisition_ids=acq, source_files=names, units="mm",
            method=method, nodata=reads[0].fill_value,
            notes=["quantity is a DERIVED accumulation from half-hourly mm/hr RATE observations (rate x 0.5 h)",
                   "dataset version is only what the file states; V07 is the Phase 2 selection, not verified here"
                   if version is None else f"version from file: {version}"])

    obs_n, exp_n = counts["observed_days"], counts["expected_days"]
    cov = [s["n_valid"] / s["n_cells"] for s in stats if s["n_cells"]]
    quality = LayerQuality(
        total_pixels=exp_n, valid_pixels=obs_n, valid_percent=100.0 * obs_n / exp_n,
        missing_percent=100.0 * (exp_n - obs_n) / exp_n,
        aoi_coverage_percent=100.0 * sum(cov) / len(cov) if cov else None,
        native_resolution={"x": res["lon"], "y": res["lat"], "unit": "degree"}, crs="EPSG:4326",
        temporal_start=counts["first_observed"], temporal_end=counts["last_observed"],
        checks_passed=["files_read"], checks_failed=[e["file"] for e in errors], warnings=list(warns))
    status = (LayerStatus.PROCESSED if not errors and not counts["missing_days"]
              else LayerStatus.PARTIALLY_PROCESSED)
    return RainfallResult(
        status=status, daily=rec["daily"], monthly=rec["monthly"], rolling=rec["rolling"], counts=counts,
        windows=[int(w) for w in windows], quality=quality,
        provenance_daily=prov("sum of 48 half-hour accumulations (AOI mean rate mm/hr x 0.5 h) per UTC day; "
                              "only days with all 48 valid intervals"),
        provenance_accumulations=prov("sum of daily totals over fully observed calendar months / trailing windows"),
        file_errors=errors, aoi_stats=stats, warnings=warns,
        input_hash=compute_input_hash(files, aoi, start, end, tuple(windows)))
