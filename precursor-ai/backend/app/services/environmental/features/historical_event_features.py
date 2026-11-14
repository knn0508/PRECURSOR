"""Historical landslide catalog features (NASA Global Landslide Catalog, Phase 2). Descriptive counts only."""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Any

from shapely.geometry import Point

EARTH_RADIUS_KM = 6371.0088  # WGS84 mean radius (IUGG)

LIMITATION = ("The NASA Global Landslide Catalog is a one-time historical export current to 2016-03-07. It is incomplete and "
              "reporting-biased; the absence of events proves nothing, and the catalog is not ground truth.")


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance on a sphere of radius EARTH_RADIUS_KM (error vs the ellipsoid up to ~0.5%)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _coord(e: dict[str, Any]) -> tuple[float, float] | None:
    lon, lat = e.get("lon"), e.get("lat")
    ok = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (lon, lat))
    return (float(lon), float(lat)) if ok and -180 <= lon <= 180 and -90 <= lat <= 90 else None


def _date(e: dict[str, Any]) -> datetime | None:
    d = e.get("event_date")
    if isinstance(d, str):
        try:
            d = datetime.fromisoformat(d)
        except ValueError:
            return None
    return d if isinstance(d, datetime) else None


def historical_event_features(events: list[dict[str, Any]], aoi_polygon: Any, centroid: tuple[float, float] | None = None) -> dict[str, Any]:
    """events: dicts with lon, lat, event_date (datetime or ISO str), optional id/location_name.
    An event ON the polygon boundary counts as inside. Events with invalid/missing coordinates or dates are counted in
    `skipped`, never repaired. Distance is from the AOI centroid (lon, lat) to the nearest INSIDE event; null when count is 0."""
    cx, cy = centroid if centroid else (aoi_polygon.centroid.x, aoi_polygon.centroid.y)
    inside, skipped = [], 0
    for e in events:
        c, d = _coord(e), _date(e)
        if c is None or d is None:
            skipped += 1
            continue
        if aoi_polygon.covers(Point(*c)):
            inside.append({"id": e.get("id"), "location": e.get("location_name"), "lon": c[0], "lat": c[1], "date": d,
                           "distance_km": haversine_km(cx, cy, *c)})
    dates = [i["date"] for i in inside]
    return {
        "count": len(inside), "skipped": skipped,
        "date_min": min(dates).isoformat() if dates else None, "date_max": max(dates).isoformat() if dates else None,
        "counts_by_year": dict(sorted(Counter(d.year for d in dates).items())),
        "locations": [{**i, "date": i["date"].isoformat()} for i in inside],
        "nearest_event_distance_km": min(i["distance_km"] for i in inside) if inside else None,
        "distance_reference": "AOI centroid, haversine, mean Earth radius 6371.0088 km",
        "limitation": LIMITATION,
        "warnings": ([f"{skipped} event(s) skipped: missing/invalid coordinates or date"] if skipped else []),
    }
