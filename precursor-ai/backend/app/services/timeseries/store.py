"""File store: data/processed/timeseries/<area_id>/<zone>/<kind>.json. Files and JSON only (no DB table, like Phase 5)."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from app.services.timeseries.types import KINDS, SeriesPoint, TimeSeries, TimeSeriesError

_ZONE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _dir(root: Path, area_id: uuid.UUID, zone: str, *, create: bool) -> Path:
    if not _ZONE.match(zone):
        raise TimeSeriesError("zone must match [A-Za-z0-9_-]{1,64}")
    d = Path(root) / "processed" / "timeseries" / str(area_id) / zone
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def write_series(root: Path, area_id: uuid.UUID, s: TimeSeries) -> Path:
    p = _dir(root, area_id, s.zone, create=True) / f"{s.kind}.json"
    doc = {"schema": "timeseries.series", "schema_version": "1.0.0", "meta": s.meta(), "notes": s.notes,
           "points": [{"time": q.time.isoformat(), "value": q.value, "source": q.source, "sensor": q.sensor, "synthetic": q.synthetic, "quality": q.quality,
                       "track": q.track, "orbit_direction": q.orbit_direction, "look_direction": q.look_direction} for q in s.points]}
    p.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return p


def read_series(root: Path, area_id: uuid.UUID, zone: str, kind: str) -> TimeSeries:
    if kind not in KINDS:
        raise TimeSeriesError(f"unknown series kind {kind!r}")
    p = _dir(root, area_id, zone, create=False) / f"{kind}.json"
    if not p.is_file():
        raise FileNotFoundError(f"no stored series {zone}/{kind} for this area")
    doc = json.loads(p.read_text(encoding="utf-8"))
    pts = [SeriesPoint(time=datetime.fromisoformat(q["time"]), value=q["value"], source=q["source"], sensor=q["sensor"], synthetic=q["synthetic"],
                       quality=q.get("quality"), track=q.get("track"), orbit_direction=q.get("orbit_direction"), look_direction=q.get("look_direction"))
           for q in doc["points"]]
    return TimeSeries(kind=kind, zone=zone, points=pts, notes=doc.get("notes", []))  # re-validated on load


def list_series(root: Path, area_id: uuid.UUID) -> list[dict]:
    base = Path(root) / "processed" / "timeseries" / str(area_id)
    if not base.is_dir():
        return []
    out = []
    for f in sorted(base.glob("*/*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8"))["meta"])
        except (OSError, KeyError, json.JSONDecodeError):
            out.append({"zone": f.parent.name, "kind": f.stem, "error": "unreadable series file"})
    return out
