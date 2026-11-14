"""NASADEM (NASADEM_HGT, 1 arc-second, 1x1 degree tiles) via CMR. Only AOI-intersecting tiles, never the global DEM."""
from __future__ import annotations

import math
import re
from typing import Any

from shapely.geometry import box

from app.services.data_acquisition.aoi import AOI
from app.services.data_acquisition.providers._cmr_common import CmrCollectionProvider
from app.services.data_acquisition.types import GranuleRecord, ProviderName, SearchQuery

_TILE = re.compile(r"[ns]\d{2}[ew]\d{3}", re.I)


def tiles_for_aoi(aoi: AOI) -> list[str]:
    """Integer-degree tile names (SW corner, e.g. 'n40e044') whose interior overlaps the AOI.
    An edge exactly on an integer degree does not select the neighbouring tile."""
    w, s, e, n = aoi.bbox
    tiles = []
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            if aoi.geometry.intersection(box(lon, lat, lon + 1, lat + 1)).area > 0:
                tiles.append(f"{'n' if lat >= 0 else 's'}{abs(lat):02d}{'e' if lon >= 0 else 'w'}{abs(lon):03d}")
    return tiles


class NASADEMDataProvider(CmrCollectionProvider):
    name = ProviderName.NASADEM

    def _short_name(self) -> str:
        return "NASADEM_HGT"

    def _product_type(self, short_name: str) -> str:
        return "DEM"

    def _collection_extra(self, umm: dict[str, Any]) -> dict[str, Any]:
        return {"note": "Static DEM (SRTM-derived, acquired Feb 2000); tiles are 1x1 degree zip files."}

    def _granule_metadata(self, umm: dict[str, Any]) -> dict[str, Any]:
        m = _TILE.search(umm.get("GranuleUR", ""))
        return {"tile": m.group(0).lower() if m else None}

    def _postfilter(self, query: SearchQuery, records: list[GranuleRecord]) -> list[GranuleRecord]:
        # CMR footprints are padded ~0.0001 deg, so edge-adjacent tiles intersect; the tile set is stricter.
        wanted = set(tiles_for_aoi(query.aoi))
        keep = [r for r in records if r.metadata.get("tile") in wanted or r.metadata.get("tile") is None]
        extra = sorted({r.metadata["tile"] for r in records} - wanted)
        if extra:
            self.last_warnings.append(f"CMR returned tiles outside the AOI tile set, dropped: {', '.join(extra)}")
        missing = sorted(wanted - {r.metadata.get("tile") for r in records})
        if missing and len(records) <= self.settings.max_granules_per_request:
            self.last_warnings.append(f"AOI needs tiles not found in the catalog: {', '.join(missing)}")
        return keep
