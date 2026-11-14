"""Shared CMR-backed provider logic for NASADEM / GPM / SMAP (single collection each).

Subclasses set `name`, implement `_short_name()` and `_product_type()`, and may override the hooks.
Catalog facts (version, concept id, temporal extent) always come from CMR, never from constants.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.services.data_acquisition import cmr
from app.services.data_acquisition.providers.base import DataProvider, ProgressCallback
from app.services.data_acquisition.storage import safe_name, target_path
from app.services.data_acquisition.types import (
    CollectionInfo,
    DownloadError,
    GranuleRecord,
    SearchQuery,
)

if TYPE_CHECKING:
    from app.core.config import Settings

_UNITS = {"B": 1, "BYTES": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
_RES = re.compile(r"\b(\d+(?:\.\d+)?)\s*(km|degree|arc second)", re.I)


def parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def https_data_url(umm: dict[str, Any]) -> str | None:
    for u in umm.get("RelatedUrls", []):
        if u.get("Type") == "GET DATA" and urlparse(u.get("URL", "")).scheme in ("http", "https"):
            return u["URL"]
    return None


def footprint(umm: dict[str, Any]) -> BaseGeometry | None:
    geom = umm.get("SpatialExtent", {}).get("HorizontalSpatialDomain", {}).get("Geometry", {})
    parts: list[BaseGeometry] = [
        box(r["WestBoundingCoordinate"], r["SouthBoundingCoordinate"], r["EastBoundingCoordinate"], r["NorthBoundingCoordinate"])
        for r in geom.get("BoundingRectangles", [])
    ]
    for p in geom.get("GPolygons", []):
        pts = p.get("Boundary", {}).get("Points", [])
        if len(pts) >= 3:
            parts.append(Polygon([(q["Longitude"], q["Latitude"]) for q in pts]))
    return unary_union(parts) if parts else None


def file_info(umm: dict[str, Any]) -> dict[str, Any]:
    """Size/format/checksum of the first listed file. Size is `exact` only when CMR gives bytes."""
    infos = umm.get("DataGranule", {}).get("ArchiveAndDistributionInformation", [])
    if not infos:
        return {}
    i = infos[0]
    out: dict[str, Any] = {"format": i.get("Format")}
    if i.get("Size") is not None:
        unit = str(i.get("SizeUnit", "B")).upper()
        out["size"] = int(i["Size"] * _UNITS.get(unit, 1))
        out["size_exact"] = unit in ("B", "BYTES")
    cs = i.get("Checksum") or {}
    out["checksum"], out["checksum_algorithm"] = cs.get("Value"), cs.get("Algorithm")
    return out


class CmrCollectionProvider(DataProvider):
    def __init__(self, settings: "Settings", auth: Any = None, download_manager: Any = None) -> None:
        super().__init__()
        self.settings = settings
        self.auth = auth
        self.download_manager = download_manager

    # ---- hooks -----------------------------------------------------------------------
    def _short_name(self) -> str | None:  # None = provider disabled; must add a warning itself
        raise NotImplementedError

    def _product_type(self, short_name: str) -> str:
        raise NotImplementedError

    def _collection_extra(self, umm: dict[str, Any]) -> dict[str, Any]:
        return {}

    def _granule_metadata(self, umm: dict[str, Any]) -> dict[str, Any]:
        return {}

    def _postfilter(self, query: SearchQuery, records: list[GranuleRecord]) -> list[GranuleRecord]:
        return records

    # ---- catalog ---------------------------------------------------------------------
    def _verified(self) -> list[CollectionInfo]:
        short = self._short_name()
        if short is None:
            return []
        out = []
        for c in cmr.find_collections(short_name=short):
            umm = c["umm"]
            if str(umm.get("ShortName", "")).lower() != short.lower():
                continue
            te = (umm.get("TemporalExtents") or [{}])[0]
            rng = (te.get("RangeDateTimes") or [{}])[0]
            doi = (umm.get("DOI") or {}).get("DOI")
            title = umm.get("EntryTitle", short)
            m = _RES.search(title)
            extra = {
                "entry_title": title,
                "provider_id": c.get("meta", {}).get("provider-id"),
                "temporal_start": rng.get("BeginningDateTime"),
                "temporal_end": rng.get("EndingDateTime"),  # absent when ongoing
                "ends_at_present": te.get("EndsAtPresentFlag"),
                "temporal_resolution": te.get("TemporalResolution"),
                "spatial_resolution_from_title": m.group(0) if m else None,
                "units": next(
                    (v for a in umm.get("AdditionalAttributes", []) if "unit" in a.get("Name", "").lower() for v in a.get("Values", [])),
                    None,
                ),
                **self._collection_extra(umm),
            }
            out.append(CollectionInfo(
                provider=self.name, short_name=short, dataset_name=title,
                product_type=self._product_type(short), version=str(umm.get("Version", "")),
                maturity=None, description=umm.get("Abstract", ""),
                documentation_url=f"https://doi.org/{doi}" if doi else None,
                concept_id=c.get("meta", {}).get("concept-id"), extra=extra,
            ))
        if not out:
            self.last_warnings.append(f"CMR returned no collection with short_name {short}; it may be unavailable or renamed.")
        return out

    def search_collections(self) -> list[CollectionInfo]:
        self.last_warnings = []
        return self._verified()

    def _record(self, item: Any) -> GranuleRecord:
        umm = item["umm"]
        ref = umm.get("CollectionReference", {})
        short = ref.get("ShortName", self._short_name() or "")
        rng = umm.get("TemporalExtent", {}).get("RangeDateTime", {})
        fi = file_info(umm)
        url = https_data_url(umm)
        dg = umm.get("DataGranule", {})
        return GranuleRecord(
            provider=self.name, granule_id=umm["GranuleUR"], collection_short_name=short,
            product_type=self._product_type(short), version=str(ref.get("Version", "")), maturity=None,
            acquisition_start=parse_dt(rng.get("BeginningDateTime")), acquisition_end=parse_dt(rng.get("EndingDateTime")),
            footprint=footprint(umm), processing_date=parse_dt(dg.get("ProductionDateTime")),
            file_format=fi.get("format") or (Path(url).suffix.lstrip(".") if url else None),
            file_size_bytes=fi.get("size"), download_url=url,
            checksum=fi.get("checksum"), checksum_algorithm=fi.get("checksum_algorithm"),
            metadata={
                "concept_id": item.get("meta", {}).get("concept-id"),
                "size_exact": fi.get("size_exact"),
                **self._granule_metadata(umm),
            },
        )

    def search_granules(self, query: SearchQuery) -> list[GranuleRecord]:
        self.last_warnings = []
        infos = self._verified()
        if not infos:
            return []
        info = max(infos, key=lambda i: i.version)
        cap = min(query.max_results, self.settings.max_granules_per_request)
        hits = cmr.find_granules(
            info.short_name, version=info.version, aoi=query.aoi, start=query.start, end=query.end, limit=cap + 1,
        )
        records = [self._record(h) for h in hits]
        records = [r for r in records if r.footprint is None or r.footprint.intersects(query.aoi.geometry)]
        records = self._postfilter(query, records)
        if len(records) > cap:
            self.last_warnings.append(f"more than {cap} granules matched, returning first {cap} (cap = min(max_results, max_granules_per_request))")
            records = records[:cap]
        return records

    def get_granule_metadata(self, granule_id: str) -> GranuleRecord | None:
        short = self._short_name()
        if short is None:
            return None
        hits = cmr.find_granules(short, limit=1, granule_ur=granule_id)
        return self._record(hits[0]) if hits else None

    # ---- download --------------------------------------------------------------------
    def download_granule(
        self, granule: GranuleRecord, dest_dir: Path | None = None, *, progress: ProgressCallback | None = None
    ) -> Path:
        if not granule.download_url:
            raise DownloadError(f"{granule.granule_id}: catalog lists no https download URL", retryable=False)
        if granule.file_size_bytes is not None and granule.file_size_bytes > self.settings.max_file_size_bytes:
            raise DownloadError(
                f"{granule.granule_id}: {granule.file_size_bytes} bytes exceeds max_file_size_bytes "
                f"({self.settings.max_file_size_bytes})", retryable=False,
            )
        if self.auth is None or self.download_manager is None:
            raise DownloadError(f"{self.name} provider has no auth/download manager configured", retryable=False)
        filename = Path(urlparse(granule.download_url).path).name or granule.granule_id
        dest = dest_dir / safe_name(filename) if dest_dir else target_path(self.settings.data_root, granule, filename)
        dest.parent.mkdir(parents=True, exist_ok=True)
        result = self.download_manager.download(
            granule.download_url, dest,
            expected_size=granule.file_size_bytes if granule.metadata.get("size_exact") else None,
            checksum=granule.checksum, checksum_algorithm=granule.checksum_algorithm,
            progress=progress, session=self.auth.get_session(),
        )
        return result.path
