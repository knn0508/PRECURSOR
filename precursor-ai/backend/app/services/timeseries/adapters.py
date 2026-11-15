"""Adapters from existing Phase 3/4 outputs to `TimeSeries`. Dates become midnight UTC explicitly. Nothing is filled."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from app.services.timeseries.types import SeriesPoint, TimeSeries, TimeSeriesError


def _utc(d: str | date) -> datetime:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def from_rainfall_daily(records: list[dict[str, Any]], zone: str, *, source: str, sensor: str, synthetic: bool) -> TimeSeries:
    """`records` = Phase 4 `series_to_records(...)["daily"]`: {"date", "precip_mm_day" (None = missing), "observed"}."""
    pts = [SeriesPoint(time=_utc(r["date"]), value=r["precip_mm_day"] if r.get("observed", True) else None, source=source, sensor=sensor, synthetic=synthetic)
           for r in records]
    return TimeSeries(kind="rainfall_mm_day", zone=zone, points=pts)


def from_values_by_date(kind: str, zone: str, rows: list[tuple[str | date, float | None]], *, source: str, sensor: str, synthetic: bool) -> TimeSeries:
    """Generic non-geometry series (for example SMAP AOI soil moisture): (date, value-or-None) rows."""
    return TimeSeries(kind=kind, zone=zone, points=[SeriesPoint(time=_utc(d), value=v, source=source, sensor=sensor, synthetic=synthetic) for d, v in rows])


def from_insar_pair_velocities(pairs: list[dict[str, Any]], zone: str, *, source: str, sensor: str, synthetic: bool) -> TimeSeries:
    """Phase 3 products are independent interferogram PAIRS, not a displacement time series (no SBAS inversion exists). Each pair gives one
    mean LOS velocity, placed at the pair's mid-time. Each dict: reference_time, secondary_time (ISO), mean_velocity_mm_yr, orbit_direction,
    track, look_direction, coherence_mean (optional). Overlapping pairs share acquisitions, so points are NOT independent (stated in notes)."""
    pts = []
    for p in sorted(pairs, key=lambda q: q["reference_time"]):
        a, b = datetime.fromisoformat(p["reference_time"]), datetime.fromisoformat(p["secondary_time"])
        if a.tzinfo is None or b.tzinfo is None:
            raise TimeSeriesError("pair times must be timezone-aware")
        pts.append(SeriesPoint(time=a + (b - a) / 2, value=p.get("mean_velocity_mm_yr"), source=source, sensor=sensor, synthetic=synthetic,
                               quality=p.get("coherence_mean"), track=p.get("track"), orbit_direction=p.get("orbit_direction"), look_direction=p.get("look_direction")))
    return TimeSeries(kind="los_velocity_mm_yr", zone=zone, points=pts,
                      notes=["each point is one interferogram pair mean velocity at its mid-time; overlapping pairs share acquisitions (not independent)"])
