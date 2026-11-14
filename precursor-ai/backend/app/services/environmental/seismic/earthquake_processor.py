"""Pure functions: USGS GeoJSON features -> validated plain dicts. Invalid input is rejected, never clamped or repaired."""
from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any


def parse_feature(f: Any) -> dict[str, Any]:
    """One USGS GeoJSON feature -> event dict. Raises ValueError (message says why) when anything required is invalid."""
    if not isinstance(f, dict):
        raise ValueError("feature is not an object")
    props, geom = f.get("properties"), f.get("geometry")
    if not isinstance(props, dict) or not isinstance(geom, dict):
        raise ValueError("missing properties or geometry")
    eid = f.get("id")
    if not isinstance(eid, str) or not eid:
        raise ValueError("missing event id")
    coords = geom.get("coordinates")
    if geom.get("type") != "Point" or not isinstance(coords, (list, tuple)) or len(coords) < 2:
        raise ValueError("geometry is not a Point with [lon, lat, depth]")
    lon, lat = coords[0], coords[1]
    for v in (lon, lat):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError("non-numeric coordinate")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"coordinate out of range lon={lon} lat={lat}")
    depth = coords[2] if len(coords) > 2 else None
    if depth is not None:
        if isinstance(depth, bool) or not isinstance(depth, (int, float)) or not math.isfinite(depth) or not -100 <= depth <= 1000:
            raise ValueError(f"invalid depth {depth!r}")  # None stays None: missing depth is never 0
    mag = props.get("mag")
    if isinstance(mag, bool) or not isinstance(mag, (int, float)) or not math.isfinite(mag) or not -10 <= mag <= 10:
        raise ValueError(f"invalid magnitude {mag!r}")
    t = props.get("time")
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t):
        raise ValueError(f"invalid time {t!r}")
    try:
        when = datetime.fromtimestamp(t / 1000.0, tz=UTC)  # USGS time = milliseconds since epoch (UTC)
    except (OverflowError, OSError, ValueError):
        raise ValueError(f"time out of range {t!r}") from None
    return {"id": eid, "time": when, "magnitude": float(mag), "mag_type": props.get("magType"),
            "depth_km": None if depth is None else float(depth), "place": props.get("place"), "url": props.get("url"),
            "status": props.get("status"), "lon": float(lon), "lat": float(lat), "properties": dict(props)}


def parse_feature_collection(doc: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """GeoJSON FeatureCollection dict -> (events, warnings). Malformed features are skipped with a warning."""
    if not isinstance(doc, dict) or not isinstance(doc.get("features"), list):
        raise ValueError("not a GeoJSON FeatureCollection")
    events, warns = [], []
    for i, f in enumerate(doc["features"]):
        try:
            events.append(parse_feature(f))
        except ValueError as e:
            warns.append(f"feature {i} (id={f.get('id') if isinstance(f, dict) else None}) skipped: {e}")
    return events, warns


def dedupe(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Drop repeated event ids, keeping the first. Returns (unique, n_dropped)."""
    seen: set[str] = set()
    out = []
    for e in events:
        if e["id"] not in seen:
            seen.add(e["id"])
            out.append(e)
    return out, len(events) - len(out)


def normalise_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate already-parsed event dicts (e.g. re-loaded), de-duplicate, sort by time then id."""
    warns, ok = [], []
    for e in events:
        t = e.get("time")
        if not (isinstance(t, datetime) and t.tzinfo is not None):
            warns.append(f"event {e.get('id')} skipped: time is not an aware datetime")
            continue
        lat, lon, m = e.get("lat"), e.get("lon"), e.get("magnitude")
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lat, lon, m)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            warns.append(f"event {e.get('id')} skipped: invalid coordinate or magnitude")
            continue
        ok.append(e)
    uniq, dropped = dedupe(ok)
    if dropped:
        warns.append(f"{dropped} duplicate event id(s) dropped")
    return sorted(uniq, key=lambda e: (e["time"], e["id"])), warns
