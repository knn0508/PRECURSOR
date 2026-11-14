"""Alternative NISAR catalog via the asf_search library (ASF's own search API).

Search only. ASF products wrap the same CMR UMM-G record, so they normalise through the same code
as the CMR provider. Downloads belong to NISARDataProvider (Earthdata auth + DownloadManager).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from shapely.geometry import Polygon, box

from app.services.data_acquisition.providers.base import DataProvider, ProgressCallback
from app.services.data_acquisition.providers.nisar import (
    _LEVEL,
    MATURITY_ORDER,
    granule_from_umm,
    short_name,
)
from app.core.config import Settings
from app.services.data_acquisition.types import (
    CollectionInfo,
    DownloadError,
    GranuleRecord,
    ProviderError,
    ProviderName,
    SearchQuery,
)

_MAX_VERTICES = 100


def asf_search(**kwargs: Any) -> list[Any]:
    """The one mockable seam over asf_search.search."""
    import asf_search as asf

    try:
        return list(asf.search(**kwargs))
    except Exception as exc:
        raise ProviderError(f"ASF search failed for {kwargs.get('shortName')}: {type(exc).__name__}: {exc}") from exc


def _intersects_with(aoi) -> str:
    g = aoi.geometry
    if isinstance(g, Polygon) and not g.interiors and len(g.exterior.coords) <= _MAX_VERTICES:
        return g.wkt
    return box(*aoi.bbox).wkt  # superset; footprints are post-filtered


class ASFSearchProvider(DataProvider):
    name = ProviderName.NISAR

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._s = settings

    def search_collections(self) -> list[CollectionInfo]:
        self.last_warnings = ["asf_search cannot enumerate collections; use NISARDataProvider.search_collections()"]
        return []

    def search_granules(self, query: SearchQuery) -> list[GranuleRecord]:
        self.last_warnings = []
        allowed = set(self._s.allowed_maturity_list)
        maturities = [m for m in MATURITY_ORDER if m in query.maturities and m.value in allowed]
        if not maturities:
            self.last_warnings.append("no maturity left after intersecting the query with allowed settings")
            return []
        products = []
        for p in (p.upper() for p in (query.product_types or self._s.nisar_product_list)):
            if p in _LEVEL:
                products.append(p)
            else:
                self.last_warnings.append(f"unknown NISAR product {p!r} ignored")
        cap = min(query.max_results, self._s.max_granules_per_request)
        wkt = _intersects_with(query.aoi)
        out: list[GranuleRecord] = []
        attempted = failed = 0
        for maturity in maturities:
            for product in products:
                if len(out) >= cap:
                    break
                sn = short_name(product, maturity)
                attempted += 1
                try:
                    found = asf_search(
                        shortName=sn, intersectsWith=wkt, start=query.start, end=query.end, maxResults=cap
                    )
                except ProviderError as exc:
                    failed += 1
                    self.last_warnings.append(f"{sn} not searchable via ASF: {exc}")
                    continue
                for p in found:
                    rec = granule_from_umm(p.umm, p.meta, short_name_=sn)
                    if rec.footprint is not None and rec.footprint.intersects(query.aoi.geometry):
                        out.append(rec)
                        if len(out) >= cap:
                            break
        if attempted and failed == attempted:
            raise ProviderError("; ".join(self.last_warnings))
        return out

    def get_granule_metadata(self, granule_id: str) -> GranuleRecord | None:
        self.last_warnings = []
        for p in asf_search(granule_list=[granule_id], maxResults=1):
            return granule_from_umm(p.umm, p.meta)
        return None

    def download_granule(
        self, granule: GranuleRecord, dest_dir: Path, *, progress: ProgressCallback | None = None
    ) -> Path:
        raise DownloadError(
            "ASFSearchProvider is search-only; download with NISARDataProvider (Earthdata auth + DownloadManager)",
            retryable=False,
        )
