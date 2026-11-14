"""Catalog events for the dataset builder (reads the Phase 2 `landslide_events` table; never writes)."""
from __future__ import annotations

import uuid
from typing import Any

from geoalchemy2 import functions as gf
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import LandslideEvent, MonitoredArea
from app.services.features_cv.types import NotAvailable

# Events slightly OUTSIDE the AOI are fetched too: their exclusion buffers must keep background samples away from the AOI edge.
DEFAULT_MARGIN_DEG = 0.25


def load_events(db: Session, area_id: uuid.UUID, margin_deg: float = DEFAULT_MARGIN_DEG) -> list[dict[str, Any]]:
    area = db.get(MonitoredArea, area_id)
    if area is None:
        raise NotAvailable("area not found")
    box = func.ST_Expand(area.geometry, margin_deg)
    rows = db.scalars(select(LandslideEvent).where(gf.ST_Intersects(LandslideEvent.geometry, box)).order_by(LandslideEvent.external_event_id)).all()
    out = []
    for r in rows:
        pt = to_shape(r.geometry)
        out.append({"id": r.external_event_id, "lon": pt.x, "lat": pt.y, "event_date": r.event_date, "original_attributes": dict(r.original_attributes or {})})
    return out
