"""Rainfall stage: daily IMERG-like files + AOI -> daily/monthly/rolling series with quality and provenance.

Tolerates missing dates, corrupt files (recorded per file, processing continues) and files outside the window.
Never interpolates, forecasts or fills missing days; there is no risk language here.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date as Date
from pathlib import Path
from typing import Any, NamedTuple

from shapely.geometry.base import BaseGeometry

from app.services.environmental.rainfall import reader as rd
from app.services.environmental.rainfall import temporal_aggregation as ta
from app.services.environmental.types import (
    DataOrigin, EnvError, LayerQuality, LayerStatus, MeasurementKind, NotAvailable, Provenance)

DATASET_NAME = "GPM_3IMERGDF"  # Phase 2 selection; the version is only reported if the file states it
ASSUMED_VERSION = "07"


class RainfallFile(NamedTuple):
    date: Date
    path: str | Path
    acquisition_id: str | None = None


@dataclass
class RainfallResult:
    status: LayerStatus
    daily: list[dict[str, Any]]
    monthly: list[dict[str, Any]]
    rolling: list[dict[str, Any]]
    counts: dict[str, Any]
    windows: list[int]
    quality: LayerQuality
    provenance_daily: Provenance  # SOURCE_OBSERVATION: the AOI value per day
    provenance_accumulations: Provenance  # DERIVED_MEASUREMENT: monthly / rolling sums
    file_errors: list[dict[str, str]]
    aoi_stats: list[dict[str, Any]]  # per observed day: n_cells, n_valid, min/max, method
    warnings: list[str]
    input_hash: str
    units: str = "mm"
    daily_units: str = "mm/day"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value, "daily": self.daily, "monthly": self.monthly, "rolling": self.rolling,
            "counts": self.counts, "windows": self.windows, "quality": self.quality.to_dict(),
            "provenance_daily": self.provenance_daily.to_dict(),
            "provenance_accumulations": self.provenance_accumulations.to_dict(),
            "file_errors": self.file_errors, "aoi_stats": self.aoi_stats, "warnings": self.warnings,
            "input_hash": self.input_hash, "units": self.units, "daily_units": self.daily_units,
        }


def compute_input_hash(files: list[RainfallFile], aoi: BaseGeometry, start: Date, end: Date,
                       windows: tuple[int, ...]) -> str:
    """Stable over file NAMES, sizes, dates, acquisition ids, AOI, window and rolling windows (no paths, no mtimes)."""
    items = []
    for f in sorted(files, key=lambda x: (x.date, Path(x.path).name)):
        p = Path(f.path)
        items.append([f.date.isoformat(), p.name, p.stat().st_size if p.exists() else None, f.acquisition_id])
    payload = {"files": items, "aoi": aoi.wkt, "start": start.isoformat(), "end": end.isoformat(),
               "windows": sorted(int(w) for w in windows)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def process_rainfall(files: list[RainfallFile], aoi: BaseGeometry, start: Date, end: Date,
                     windows: tuple[int, ...] = ta.DEFAULT_WINDOWS) -> RainfallResult:
    warns: list[str] = []
    errors: list[dict[str, str]] = []
    obs: list[tuple[Date, float | None]] = []
    stats: list[dict[str, Any]] = []
    used: list[RainfallFile] = []
    reads: list[rd.DailyAoi] = []

    for f in files:
        name = Path(f.path).name
        if f.date < start or f.date > end:
            warns.append(f"{name}: date {f.date.isoformat()} outside window {start}..{end}: ignored")
            continue
        try:
            r = rd.read_daily_aoi(f.path, aoi, f.date)
        except (EnvError, NotAvailable) as e:
            errors.append({"file": name, "date": f.date.isoformat(), "error": str(e)})
            continue
        reads.append(r)
        used.append(f)
        obs.append((f.date, r.stat.mean_mm_day))
        warns += [f"{name}: {w}" for w in r.warnings]
        stats.append({"date": f.date.isoformat(), "n_cells": r.stat.n_cells, "n_valid": r.stat.n_valid,
                      "min_mm_day": r.stat.min_mm_day, "max_mm_day": r.stat.max_mm_day, "method": r.stat.method})

    if not any(v is not None for _, v in obs):
        detail = "; ".join(f"{e['file']}: {e['error']}" for e in errors[:3])
        raise NotAvailable("no usable rainfall file for the AOI and window" + (f" ({detail})" if detail else ""))

    daily, w2 = ta.build_daily_series(obs, start, end)  # EnvError on conflicting duplicates
    warns += w2
    monthly = ta.monthly_accumulation(daily)
    rolling = ta.rolling_accumulation(daily, windows)
    counts = ta.summary_counts(daily)
    rec = ta.series_to_records(daily, rolling, monthly)
    if counts["missing_days"]:
        warns.append(f"{counts['missing_days']} of {counts['expected_days']} days are missing and were NOT filled; "
                     "sums are only reported for fully observed months/windows")
    warns.append("AOI value is a ~0.1 degree cell statistic (satellite estimate); resolution is not increased")

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
    first, last = counts["first_observed"], counts["last_observed"]

    def prov(kind: MeasurementKind, units: str, method: str) -> Provenance:
        return Provenance(
            provider="GPM", dataset_name=DATASET_NAME, dataset_version=version, origin=origin, measurement_kind=kind,
            acquisition_ids=acq, source_files=names, units=units, method=method, nodata=reads[0].fill_value,
            notes=["dataset version is only what the file states; V07 is the Phase 2 selection, not verified here"
                   if version is None else f"version from file: {version}"])

    obs_n, exp_n = counts["observed_days"], counts["expected_days"]
    # "aoi coverage": mean share of AOI cells that were valid on observed days
    cov = [s["n_valid"] / s["n_cells"] for s in stats if s["n_cells"]]
    quality = LayerQuality(
        total_pixels=exp_n, valid_pixels=obs_n, valid_percent=100.0 * obs_n / exp_n,
        missing_percent=100.0 * (exp_n - obs_n) / exp_n,
        aoi_coverage_percent=100.0 * sum(cov) / len(cov) if cov else None,
        native_resolution={"x": res["lon"], "y": res["lat"], "unit": "degree"}, crs="EPSG:4326",
        temporal_start=first, temporal_end=last,
        checks_passed=["files_read"] if reads else [], checks_failed=[e["file"] for e in errors],
        warnings=list(warns))
    status = LayerStatus.PROCESSED if not errors and not counts["missing_days"] else LayerStatus.PARTIALLY_PROCESSED
    return RainfallResult(
        status=status, daily=rec["daily"], monthly=rec["monthly"], rolling=rec["rolling"], counts=counts,
        windows=[int(w) for w in windows], quality=quality,
        provenance_daily=prov(MeasurementKind.SOURCE_OBSERVATION, "mm/day", "AOI mean of valid IMERG cells"),
        provenance_accumulations=prov(MeasurementKind.DERIVED_MEASUREMENT, "mm",
                                      "sum of daily mm/day over fully observed calendar months / trailing windows"),
        file_errors=errors, aoi_stats=stats, warnings=warns,
        input_hash=compute_input_hash(files, aoi, start, end, tuple(windows)))
