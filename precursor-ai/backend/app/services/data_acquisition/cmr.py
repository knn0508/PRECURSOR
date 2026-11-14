"""Thin wrapper over earthaccess/CMR so providers share ONE mockable seam.

Public catalog search needs no Earthdata login. Tests patch `find_collections` / `find_granules`
(never the network). Returned items are earthaccess objects (dict-like: item["umm"], item["meta"]).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.polygon import orient

from app.services.data_acquisition.aoi import AOI
from app.services.data_acquisition.types import ProviderError

log = logging.getLogger(__name__)

MAX_POLYGON_VERTICES = 100  # CMR rejects very large polygons in query strings


def aoi_query_args(aoi: AOI) -> dict[str, Any]:
    """CMR spatial arguments: an exact polygon when it is simple enough, else the bounding box.

    Callers MUST still post-filter returned footprints with shapely (bbox is a superset).
    """
    geom = aoi.geometry
    if isinstance(geom, Polygon) and not geom.interiors and len(geom.exterior.coords) <= MAX_POLYGON_VERTICES:
        ring = orient(geom, 1.0).exterior.coords  # CMR wants counter-clockwise
        return {"polygon": [(float(x), float(y)) for x, y in ring]}
    if isinstance(geom, (Polygon, MultiPolygon)):
        w, s, e, n = aoi.bbox
        return {"bounding_box": (w, s, e, n)}
    raise ProviderError("unsupported AOI geometry")


def find_collections(**kwargs: Any) -> list[Any]:
    """earthaccess.search_datasets(**kwargs): e.g. short_name='NISAR_L2_GUNW_V1' or keyword=..."""
    import earthaccess

    try:
        return list(earthaccess.search_datasets(**kwargs))
    except Exception as exc:  # network/CMR errors surface as many types
        raise ProviderError(f"CMR collection search failed: {type(exc).__name__}: {exc}") from exc


def find_granules(
    short_name: str,
    *,
    version: str | None = None,
    aoi: AOI | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 10,
    **extra: Any,
) -> list[Any]:
    """earthaccess.search_data for one collection. `count` caps results at `limit`."""
    import earthaccess

    args: dict[str, Any] = {"short_name": short_name, "count": limit, **extra}
    if version:
        args["version"] = version
    if aoi is not None:
        args.update(aoi_query_args(aoi))
    if start or end:
        args["temporal"] = (start.isoformat() if start else "", end.isoformat() if end else "")
    try:
        return list(earthaccess.search_data(**args))
    except Exception as exc:
        raise ProviderError(f"CMR granule search failed for {short_name}: {type(exc).__name__}: {exc}") from exc
