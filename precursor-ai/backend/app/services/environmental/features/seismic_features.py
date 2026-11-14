"""Seismic features from validated USGS event dicts. Descriptive only; no causation, no hazard scores."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np

from app.services.environmental.features.historical_event_features import haversine_km

NOTE = "Earthquakes are independent observations; nothing here implies they caused or will cause landslides."
DEFAULT_BINS = (0.0, 3.0, 4.0, 5.0, 6.0, 7.0, 10.0)  # magnitude bin edges [lo, hi), last bin closed


def seismic_features(events: list[dict[str, Any]], centroid: tuple[float, float], start: datetime | None = None,
                     end: datetime | None = None, bins: tuple[float, ...] = DEFAULT_BINS) -> dict[str, Any]:
    """events: dicts from earthquake_processor (aware `time`). Window [start, end] inclusive; centroid = (lon, lat).
    Events below bins[0] or above bins[-1] are reported in `histogram_outside` (not dropped)."""
    ev = [e for e in events if (start is None or e["time"] >= start) and (end is None or e["time"] <= end)]
    mags = np.array([e["magnitude"] for e in ev], dtype=float)
    depths = [e["depth_km"] for e in ev if e.get("depth_km") is not None]
    hist = np.histogram(mags, bins=list(bins))[0].tolist() if len(ev) else [0] * (len(bins) - 1)
    locs = [{"id": e["id"], "lon": e["lon"], "lat": e["lat"], "place": e.get("place"), "time": e["time"].isoformat(),
             "magnitude": e["magnitude"], "depth_km": e.get("depth_km"), "distance_km": haversine_km(*centroid, e["lon"], e["lat"])}
            for e in ev]
    return {
        "count": len(ev),
        "magnitude": {"min": float(mags.min()), "max": float(mags.max()), "mean": float(mags.mean())} if len(ev) else None,
        "magnitude_histogram": {"bin_edges": list(bins), "counts": hist, "outside": int(len(ev) - sum(hist))},
        "depth_km": {"min": min(depths), "max": max(depths), "n_with_depth": len(depths)} if depths else None,
        "locations": locs,
        "nearest_event_distance_km": min(l["distance_km"] for l in locs) if locs else None,
        "distance_reference": "AOI centroid, haversine, mean Earth radius 6371.0088 km",
        "note": NOTE, "warnings": [],
    }
