"""USGS Earthquake Catalog (FDSN event API) provider.

Verified from https://earthquake.usgs.gov/fdsnws/event/1/ : params starttime/endtime/min|max latitude|longitude/minmagnitude/
limit (1-20000)/offset (default 1)/orderby/format; >20000 results -> HTTP 400; `count` and `query` methods.
GeoJSON field list (mag, place, time, url, status, magType, type, net, ids; coordinates lon,lat,depth) verified at
https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php. NOT stated in those pages: that time is epoch MILLISECONDS
and depth is km (taken from common USGS usage), any numeric rate limit, and whether offset+limit may exceed 20000.
Credit requested by USGS ("U.S. Geological Survey"); USGS-authored data are public domain.

`fetch` is the ONLY network call in this phase: anonymous read-only GETs of small JSON. The session is injectable.
"""
from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.environmental.providers.base import AcquisitionProposal, BBox, EnvironmentalProvider, aoi_bounds
from app.services.environmental.seismic.earthquake_processor import dedupe, parse_feature_collection
from app.services.environmental.storage import external_dir
from app.services.environmental.types import EnvError, NotAvailable

BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/"
MAX_PAGE = 20000
ATTRIBUTION = "Credit: U.S. Geological Survey (USGS-authored data are U.S. public domain)"


@dataclass
class FetchResult:
    events: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False
    pages: int = 0


def _iso(d: datetime) -> str:
    if d.tzinfo is None:
        raise EnvError("start/end must be timezone-aware")
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


class USGSEarthquakeProvider(EnvironmentalProvider):
    name = "usgs"

    def __init__(self, *, timeout: float = 30.0, max_retries: int = 3, backoff_s: float = 1.0,
                 page_size: int = 5000, max_records: int = 50000, sleep=_time.sleep) -> None:
        if not 1 <= page_size <= MAX_PAGE:
            raise ValueError(f"page_size must be 1..{MAX_PAGE}")
        self.timeout, self.max_retries, self.backoff_s = timeout, max_retries, backoff_s
        self.page_size, self.max_records, self._sleep = page_size, max_records, sleep

    def describe(self) -> dict[str, Any]:
        return {"provider": "USGS", "dataset": "USGS Earthquake Catalog (FDSN event web service)", "base_url": BASE_URL,
                "max_results_per_query": MAX_PAGE, "format": "geojson", "auth_required": False,
                "licence": ATTRIBUTION,
                "verified": ["query parameters", "20000 limit and HTTP 400", "count/query methods", "GeoJSON property names", "coordinate order"],
                "not_verified": ["time is epoch ms and depth is km (not stated on the fetched pages)", "numeric rate limit (none stated)",
                                 "behaviour of offset beyond 20000"],
                "implementation_status": "IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA",
                "capabilities": "read-only paginated fetch (fake-session tested), local GeoJSON reader"}

    def plan_acquisition(self, aoi: Any, start: datetime | None = None, end: datetime | None = None,
                         min_magnitude: float | None = None, **_: Any) -> AcquisitionProposal:
        bbox = aoi_bounds(aoi)
        q = f"{BASE_URL}count?format=geojson&minlatitude={bbox[1]}&maxlatitude={bbox[3]}&minlongitude={bbox[0]}&maxlongitude={bbox[2]}"
        return AcquisitionProposal(
            provider="USGS", dataset="USGS Earthquake Catalog", version=None, source_urls=[BASE_URL, q], aoi_bbox=bbox,
            expected_file_count=None, estimated_size_mb=None,
            size_basis="unknown until the `count` method is called; GeoJSON is roughly 1 KB per event (assumption)",
            requires_auth=False, auth_note="Anonymous; no credentials.",
            intended_use="Independent seismic observations in a window; no causal link to landslides is implied.",
            destination="data/external/usgs/ (optional saved GeoJSON)",
            notes=[ATTRIBUTION, "fetch() makes read-only GET requests; this plan made none."])

    def local_inputs(self, data_root: Path, aoi: Any) -> list[Path]:
        d = external_dir(data_root, "usgs")
        return sorted(d.glob("*.geojson")) + sorted(d.glob("*.json")) if d.is_dir() else []

    def read_local(self, files: list[Path], aoi: Any = None, **_: Any) -> FetchResult:
        import json
        if not files:
            raise NotAvailable("no local USGS GeoJSON files")
        events, warns = [], []
        for f in files:
            ev, w = parse_feature_collection(json.loads(Path(f).read_text(encoding="utf-8")))
            events += ev
            warns += w
        events, dropped = dedupe(events)
        if dropped:
            warns.append(f"{dropped} duplicate event id(s) dropped")
        return FetchResult(events, warns)

    # --- the one network method -------------------------------------------------
    def _get(self, session: Any, params: dict[str, Any]) -> dict[str, Any]:
        last = ""
        for attempt in range(self.max_retries + 1):
            try:
                r = session.get(BASE_URL + "query", params=params, timeout=self.timeout)
            except Exception as e:  # noqa: BLE001  transport errors of any session implementation (timeouts, resets)
                last = f"transport error: {type(e).__name__}"
            else:
                if r.status_code == 200:
                    try:
                        return r.json()
                    except ValueError:
                        last = "invalid JSON body"
                elif r.status_code == 400:
                    raise _BadRequest(f"HTTP 400 (bad parameters or more than {MAX_PAGE} results)")
                elif r.status_code == 429 or r.status_code >= 500:
                    last = f"HTTP {r.status_code}"
                    ra = (getattr(r, "headers", None) or {}).get("Retry-After")
                    if ra and str(ra).isdigit() and attempt < self.max_retries:
                        self._sleep(min(float(ra), 60.0))
                        continue
                else:
                    raise EnvError(f"USGS request failed: HTTP {r.status_code}")
            if attempt < self.max_retries:
                self._sleep(self.backoff_s * 2 ** attempt)
        raise EnvError(f"USGS request failed after {self.max_retries + 1} attempts: {last}")

    def fetch(self, bbox: BBox, start: datetime, end: datetime, min_magnitude: float | None = None,
              session: Any = None) -> FetchResult:
        w, s, e, n = aoi_bounds(bbox)
        if end <= start:
            raise EnvError("end must be after start")
        if session is None:
            import requests
            session = requests.Session()
        base = {"format": "geojson", "starttime": _iso(start), "endtime": _iso(end), "minlongitude": w, "minlatitude": s,
                "maxlongitude": e, "maxlatitude": n, "orderby": "time-asc", "limit": self.page_size}
        if min_magnitude is not None:
            base["minmagnitude"] = min_magnitude
        res, offset = FetchResult([]), 1
        while True:
            try:
                doc = self._get(session, {**base, "offset": offset})
            except _BadRequest as ex:
                if offset == 1:
                    raise EnvError(str(ex)) from None
                res.truncated = True  # later page refused: keep what we have, say so
                res.warnings.append(f"{ex} at offset {offset}; results truncated, narrow the window or raise min_magnitude")
                break
            res.pages += 1
            raw = doc.get("features") if isinstance(doc, dict) else None
            if not isinstance(raw, list):
                raise EnvError("USGS response is not a GeoJSON FeatureCollection")
            ev, warns = parse_feature_collection(doc)
            res.events += ev
            res.warnings += warns
            if len(raw) < self.page_size:
                break
            offset += self.page_size
            if len(res.events) >= self.max_records:
                res.truncated = True
                res.events = res.events[: self.max_records]
                res.warnings.append(f"stopped at cap of {self.max_records} records; results truncated")
                break
        res.events, dropped = dedupe(res.events)
        if dropped:
            res.warnings.append(f"{dropped} duplicate event id(s) dropped")
        return res


class _BadRequest(Exception):
    pass
