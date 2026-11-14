"""SMAP stage: daily SMAP L3 files + AOI -> complete daily calendar of AM/PM AOI soil moisture with quality and provenance.

Missing days are None (never zero). No interpolation, gap filling, smoothing, forecast, anomaly or percentile scoring.
Conflicting duplicate dates raise EnvError (no silent choice); identical duplicates are collapsed with a warning.
"""
from __future__ import annotations

import app.core.geo_env  # noqa: F401

import hashlib
import json
from dataclasses import dataclass
from datetime import date as Date, timedelta
from pathlib import Path
from typing import Any, NamedTuple

from shapely.geometry.base import BaseGeometry

from app.services.environmental.smap import reader as rd
from app.services.environmental.types import (
    DataOrigin, EnvError, LayerQuality, LayerStatus, MeasurementKind, NotAvailable, Provenance)

DATASET_NAME = "SPL3SMP_E"  # Phase 2 default collection (settings.smap_collection); version only if the file states it
UNITS = "cm3/cm3"  # volumetric fraction; NSIDC documents m3/m3 (numerically identical, no conversion applied)


class SmapFile(NamedTuple):
    date: Date
    path: str | Path
    acquisition_id: str | None = None


@dataclass
class SmapResult:
    status: LayerStatus
    daily: list[dict[str, Any]]
    counts: dict[str, Any]
    quality: LayerQuality
    provenance: Provenance
    file_errors: list[dict[str, str]]
    aoi_stats: list[dict[str, Any]]  # per observed day and overpass
    warnings: list[str]
    input_hash: str
    quality_filter: bool
    quality_dropped_cells: int  # valid cell-values removed by the filter (sum over used overpass-days)
    units: str = UNITS

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value, "daily": self.daily, "counts": self.counts, "quality": self.quality.to_dict(),
            "provenance": self.provenance.to_dict(), "file_errors": self.file_errors, "aoi_stats": self.aoi_stats,
            "warnings": self.warnings, "input_hash": self.input_hash, "quality_filter": self.quality_filter,
            "quality_dropped_cells": self.quality_dropped_cells, "units": self.units,
        }


def compute_input_hash(files: list[SmapFile], aoi: BaseGeometry, start: Date, end: Date, quality_filter: bool) -> str:
    """Stable over file NAMES, sizes, dates, acquisition ids, AOI, window and quality_filter (no paths, no mtimes)."""
    items = []
    for f in sorted(files, key=lambda x: (x.date, Path(x.path).name)):
        p = Path(f.path)
        items.append([f.date.isoformat(), p.name, p.stat().st_size if p.exists() else None, f.acquisition_id])
    payload = {"files": items, "aoi": aoi.wkt, "start": start.isoformat(), "end": end.isoformat(),
               "quality_filter": bool(quality_filter)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _missing_ranges(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(days):
        if not days[i]["observed"]:
            j = i
            while j + 1 < len(days) and not days[j + 1]["observed"]:
                j += 1
            out.append({"start": days[i]["date"], "end": days[j]["date"], "days": j - i + 1})
            i = j + 1
        else:
            i += 1
    return out


def process_smap(files: list[SmapFile], aoi: BaseGeometry, start: Date, end: Date, *,
                 quality_filter: bool = False) -> SmapResult:
    if end < start:
        raise EnvError("end date precedes start date")
    warns: list[str] = []
    errors: list[dict[str, str]] = []
    stats: list[dict[str, Any]] = []
    reads: dict[Date, tuple[rd.DailySmap, SmapFile]] = {}
    dropped = 0

    for f in files:
        name = Path(f.path).name
        if f.date < start or f.date > end:
            warns.append(f"{name}: date {f.date.isoformat()} outside window {start}..{end}: ignored")
            continue
        try:
            r = rd.read_daily_aoi(f.path, aoi, f.date, quality_filter)
        except (EnvError, NotAvailable) as e:
            errors.append({"file": name, "date": f.date.isoformat(), "error": str(e)})
            continue
        if f.date in reads:
            prev = reads[f.date][0]
            same = all((prev.overpasses[o] and prev.overpasses[o].mean) == (r.overpasses[o] and r.overpasses[o].mean)
                       for o in ("am", "pm"))
            if not same:
                raise EnvError(f"duplicate date {f.date.isoformat()} with different values ({name})")
            warns.append(f"{name}: duplicate date {f.date.isoformat()} with identical values: counted once")
            continue
        reads[f.date] = (r, f)
        warns += [f"{name}: {w}" for w in r.warnings]
        for ov, s in r.overpasses.items():
            if s is None:
                continue
            dropped += s.n_dropped_quality
            stats.append({"date": f.date.isoformat(), "overpass": ov, "n_cells": s.n_cells, "n_valid": s.n_valid,
                          "n_dropped_quality": s.n_dropped_quality, "min": s.min, "max": s.max, "method": s.method})

    if not any(s.mean is not None for r, _ in reads.values() for s in r.overpasses.values() if s):
        detail = "; ".join(f"{e['file']}: {e['error']}" for e in errors[:3])
        raise NotAvailable("no usable SMAP file for the AOI and window" + (f" ({detail})" if detail else ""))

    daily: list[dict[str, Any]] = []
    d = start
    while d <= end:
        r = reads[d][0] if d in reads else None
        am, pm = (r.overpasses.get("am") if r else None), (r.overpasses.get("pm") if r else None)
        vam = am.mean if am else None
        vpm = pm.mean if pm else None
        daily.append({
            "date": d.isoformat(), "soil_moisture_am": vam, "soil_moisture_pm": vpm,
            # combined day mean ONLY when both overpasses are observed; a missing overpass is never a zero
            "soil_moisture": (vam + vpm) / 2.0 if vam is not None and vpm is not None else None,
            "observed": vam is not None or vpm is not None,
            "n_cells_am": am.n_cells if am else None, "n_cells_pm": pm.n_cells if pm else None})
        d += timedelta(days=1)

    obs_days = [x for x in daily if x["observed"]]
    exp_n, obs_n = len(daily), len(obs_days)
    counts = {
        "expected_days": exp_n, "observed_days": obs_n, "missing_days": exp_n - obs_n,
        "first_observed": obs_days[0]["date"] if obs_days else None,
        "last_observed": obs_days[-1]["date"] if obs_days else None,
        "missing_ranges": _missing_ranges(daily),
        "observed_am_days": sum(x["soil_moisture_am"] is not None for x in daily),
        "observed_pm_days": sum(x["soil_moisture_pm"] is not None for x in daily),
        "days_with_both_overpasses": sum(x["soil_moisture"] is not None for x in daily),
    }
    if counts["missing_days"]:
        warns.append(f"{counts['missing_days']} of {exp_n} days have no valid overpass and were NOT filled")
    warns.append("a day is observed if AM or PM has a valid AOI value; the combined value is the mean of AM and PM "
                 "only when both are observed, otherwise it is missing")
    warns.append("SMAP L-band soil moisture represents about the top 5 cm of soil (NSIDC), on a 9 km grid derived from "
                 "a ~36 km radiometer footprint: not slope-scale or root-zone soil moisture")
    if quality_filter:
        warns.append(f"quality filter ON (retrieval_qual_flag bit 0 == 0): {dropped} valid cell-values dropped")
    else:
        warns.append("quality filter OFF: cells not of recommended quality are included")

    rlist = [r for r, _ in reads.values()]
    synthetic = [r.synthetic for r in rlist]
    used = [u for _, u in reads.values()]
    if all(synthetic):
        origin = DataOrigin.SYNTHETIC_FIXTURE
        warns.append("SYNTHETIC test fixture: not real soil moisture")
    elif any(synthetic):
        origin = DataOrigin.SYNTHETIC_FIXTURE
        warns.append("input mixes synthetic and non-synthetic files: labelled SYNTHETIC_FIXTURE")
    else:
        origin = DataOrigin.REAL_SATELLITE if all(u.acquisition_id for u in used) else DataOrigin.LOCAL_UNVERIFIED
    versions = {r.dataset_version for r in rlist if r.dataset_version}
    version = versions.pop() if len(versions) == 1 else None
    if versions:
        warns.append("files report different product versions")
    names = {r.dataset_name for r in rlist if r.dataset_name}
    ds_name = names.pop() if len(names) == 1 else DATASET_NAME
    prov = Provenance(
        provider="SMAP", dataset_name=ds_name, dataset_version=version, origin=origin,
        measurement_kind=MeasurementKind.SOURCE_OBSERVATION,
        acquisition_ids=sorted({u.acquisition_id for u in used if u.acquisition_id}),
        source_files=sorted({Path(u.path).name for u in used}), units=UNITS,
        method=f"AOI mean of valid SMAP cells per overpass (quality_filter={quality_filter})",
        nodata=rlist[0].fill_value,
        notes=["version from file" if version else "dataset version UNKNOWN (not stated in the file)",
               "NSIDC documents units as m3/m3; cm3/cm3 is numerically identical (no conversion applied)"])

    res = rlist[0].native_resolution_deg
    cov = [s["n_valid"] / s["n_cells"] for s in stats if s["n_cells"]]
    first_err = [e["file"] for e in errors]
    quality = LayerQuality(
        total_pixels=exp_n, valid_pixels=obs_n, valid_percent=100.0 * obs_n / exp_n,
        missing_percent=100.0 * (exp_n - obs_n) / exp_n,
        aoi_coverage_percent=100.0 * sum(cov) / len(cov) if cov else None,
        native_resolution={"x": res["lon"], "y": res["lat"], "unit": "degree", "nominal_km": rlist[0].native_resolution_km},
        crs="EPSG:4326", temporal_start=counts["first_observed"], temporal_end=counts["last_observed"],
        checks_passed=["files_read"], checks_failed=first_err, warnings=list(warns))
    status = LayerStatus.PROCESSED if not errors and not counts["missing_days"] else LayerStatus.PARTIALLY_PROCESSED
    return SmapResult(
        status=status, daily=daily, counts=counts, quality=quality, provenance=prov, file_errors=errors,
        aoi_stats=stats, warnings=warns, input_hash=compute_input_hash(files, aoi, start, end, quality_filter),
        quality_filter=quality_filter, quality_dropped_cells=dropped)


__all__ = ["SmapFile", "SmapResult", "process_smap", "compute_input_hash", "DATASET_NAME"]
