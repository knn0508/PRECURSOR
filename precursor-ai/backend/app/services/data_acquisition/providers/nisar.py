"""NISAR via NASA CMR (anonymous search) + Earthdata-authenticated download.

Collection names follow NISAR_{L2|L3}_{PRODUCT}[_PROVISIONAL|_BETA]_V1; the unsuffixed name is the
VALIDATED one. Existence is always verified against the live catalog, never assumed (e.g. there is
no VALIDATED SME2 collection). Granules of different maturities are never merged silently: every
GranuleRecord carries its maturity and collection short name.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from shapely.geometry import MultiPolygon, Polygon

from app.core.config import Settings
from app.services.data_acquisition import cmr, storage
from app.services.data_acquisition.authentication import EarthdataAuthenticationService
from app.services.data_acquisition.providers.base import DataProvider, ProgressCallback
from app.services.data_acquisition.types import (
    CollectionInfo,
    DownloadError,
    GranuleRecord,
    Maturity,
    ProviderError,
    ProviderName,
    SearchQuery,
)

log = logging.getLogger(__name__)

VERSION = "1"
DOCS_URL = "https://nisar-docs.asf.alaska.edu/"
MATURITY_ORDER = (Maturity.VALIDATED, Maturity.PROVISIONAL, Maturity.BETA)
_LEVEL = {"GUNW": "L2", "GCOV": "L2", "GSLC": "L2", "GOFF": "L2", "SME2": "L3"}
_NAME = re.compile(r"^NISAR_(?:L2|L3)_([A-Z0-9]+?)(?:_(PROVISIONAL|BETA))?_V\d+$")


def short_name(product: str, maturity: Maturity) -> str:
    suffix = "" if maturity is Maturity.VALIDATED else f"_{maturity.value}"
    return f"NISAR_{_LEVEL[product]}_{product}{suffix}_V{VERSION}"


def parse_short_name(name: str) -> tuple[str, Maturity] | None:
    m = _NAME.match(name or "")
    return (m.group(1), Maturity(m.group(2) or "VALIDATED")) if m else None


# ---- UMM-G normalisation (shared with the ASF provider; ASF products expose .umm/.meta too) ----
def _dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _footprint(umm: dict) -> Polygon | MultiPolygon | None:
    try:
        polys = umm["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"]
        shapes = [
            Polygon([(p["Longitude"], p["Latitude"]) for p in g["Boundary"]["Points"]]).buffer(0) for g in polys
        ]
    except (KeyError, TypeError, ValueError):
        return None
    shapes = [s for s in shapes if not s.is_empty]
    if not shapes:
        return None
    return shapes[0] if len(shapes) == 1 else MultiPolygon([p for s in shapes for p in getattr(s, "geoms", [s])])


def granule_from_umm(umm: dict, meta: dict, *, short_name_: str | None = None) -> GranuleRecord:
    """Normalise a CMR UMM-G granule. Missing/odd fields become None; never raises on shape."""
    umm, meta = umm or {}, meta or {}
    sn = short_name_ or (umm.get("CollectionReference") or {}).get("ShortName") or ""
    parsed = parse_short_name(sn)
    attrs: dict[str, list] = {}
    for a in umm.get("AdditionalAttributes") or []:
        if isinstance(a, dict) and a.get("Name"):
            attrs[a["Name"]] = a.get("Values") or []

    def attr(name: str) -> str | None:
        v = attrs.get(name)
        return str(v[0]) if v else None

    rng = (umm.get("TemporalExtent") or {}).get("RangeDateTime") or {}
    data_file = next(
        (
            f
            for f in (umm.get("DataGranule") or {}).get("ArchiveAndDistributionInformation") or []
            if isinstance(f, dict) and (str(f.get("Name", "")).endswith(".h5") or f.get("Format") == "HDF5")
        ),
        {},
    )
    checksum = data_file.get("Checksum") or {}
    urls = [u for u in umm.get("RelatedUrls") or [] if isinstance(u, dict)]
    h5 = [u.get("URL", "") for u in urls if u.get("Type") == "GET DATA" and str(u.get("URL", "")).startswith("https://")]
    download_url = next((u for u in h5 if u.endswith(".h5")), h5[0] if h5 else None)
    orbits = umm.get("OrbitCalculatedSpatialDomains") or [{}]
    pol = attrs.get("FREQUENCY_A_POLARIZATION", []) + attrs.get("FREQUENCY_B_POLARIZATION", [])

    meta_out: dict[str, Any] = {
        "concept_id": meta.get("concept-id"),
        "reference_start": _dt(attr("REFERENCE_ZERO_DOPPLER_START_TIME")),
        "reference_end": _dt(attr("REFERENCE_ZERO_DOPPLER_END_TIME")),
        "secondary_start": _dt(attr("SECONDARY_ZERO_DOPPLER_START_TIME")),
        "secondary_end": _dt(attr("SECONDARY_ZERO_DOPPLER_END_TIME")),
        "polarization": pol,
        "frame": _int(attr("FRAME_NUMBER")),
        "track": _int(attr("TRACK_NUMBER")),
        "orbit_number": _int((orbits[0] or {}).get("OrbitNumber")),
        "processing_center": attr("PROCESSING_CENTER"),
        "orbit_type": attr("ORBIT_TYPE"),
        "full_frame": attr("FULL_FRAME"),
        "joint_observation": attr("JOINT_OBSERVATION"),
        "product_version": attr("PRODUCT_VERSION"),
        "pge_version": (umm.get("PGEVersionClass") or {}).get("PGEVersion"),
        "input_granules": umm.get("InputGranules") or [],
    }
    return GranuleRecord(
        provider=ProviderName.NISAR,
        granule_id=umm.get("GranuleUR") or "",
        collection_short_name=sn,
        product_type=attr("PRODUCT_TYPE") or (parsed[0] if parsed else ""),
        version=VERSION,
        maturity=parsed[1] if parsed else None,
        acquisition_start=_dt(rng.get("BeginningDateTime")),
        acquisition_end=_dt(rng.get("EndingDateTime")),
        footprint=_footprint(umm),
        processing_date=_dt(((umm.get("DataGranule") or {}).get("ProductionDateTime"))),
        orbit_direction=attr("ASCENDING_DESCENDING"),
        relative_orbit=_int(attr("TRACK_NUMBER")),
        file_format=data_file.get("Format"),
        file_size_bytes=_int(data_file.get("SizeInBytes")),
        download_url=download_url,
        checksum=checksum.get("Value"),
        checksum_algorithm=checksum.get("Algorithm"),
        metadata=meta_out,
    )


class NISARDataProvider(DataProvider):
    name = ProviderName.NISAR

    def __init__(
        self,
        settings: Settings,
        auth: EarthdataAuthenticationService,
        download_manager: Any | None = None,
        *,
        fallback: DataProvider | None = None,
    ) -> None:
        super().__init__()
        self._s, self._auth, self._dm, self._fallback = settings, auth, download_manager, fallback

    def _products(self, products: list[str] | tuple[str, ...]) -> list[str]:
        out: list[str] = []
        for p in products:
            p = p.upper()
            if p not in _LEVEL:
                self.last_warnings.append(f"unknown NISAR product {p!r} ignored")
            elif p not in out:
                out.append(p)
        return out

    # ---- catalog -------------------------------------------------------------------------
    def search_collections(self) -> list[CollectionInfo]:
        self.last_warnings = []
        found: list[CollectionInfo] = []
        attempted = failed = 0
        for product in self._products(self._s.nisar_product_list):
            present: list[Maturity] = []
            lookup_failed = False
            for maturity in MATURITY_ORDER:
                sn = short_name(product, maturity)
                attempted += 1
                try:
                    hits = cmr.find_collections(short_name=sn)
                except ProviderError as exc:
                    failed += 1
                    lookup_failed = True
                    self.last_warnings.append(f"collection {sn} lookup failed: {exc}")
                    continue
                if not hits:
                    continue
                present.append(maturity)
                found.append(self._collection_info(product, maturity, sn, hits[0]))
            if lookup_failed:
                continue  # absence is only reported when every lookup for the product succeeded
            if not present:
                self.last_warnings.append(f"no collection exists for {product} in any maturity")
            elif Maturity.VALIDATED not in present:
                self.last_warnings.append(f"no VALIDATED collection exists for {product}")
        if attempted and failed == attempted:
            raise ProviderError("; ".join(self.last_warnings))
        return found

    def _collection_info(self, product: str, maturity: Maturity, sn: str, hit: Any) -> CollectionInfo:
        umm, meta = hit["umm"], hit["meta"]
        declared = str(umm.get("DataMaturity") or "").upper()
        if declared and declared != maturity.value:
            self.last_warnings.append(f"{sn}: name implies {maturity.value} but catalog DataMaturity is {declared}")
        return CollectionInfo(
            provider=ProviderName.NISAR,
            short_name=sn,
            dataset_name=umm.get("EntryTitle") or sn,
            product_type=product,
            version=str(umm.get("Version") or VERSION),
            maturity=maturity,
            description=(umm.get("Abstract") or "")[:500],
            documentation_url=DOCS_URL,
            concept_id=meta.get("concept-id"),
        )

    def search_granules(self, query: SearchQuery) -> list[GranuleRecord]:
        self.last_warnings = []
        allowed = set(self._s.allowed_maturity_list)
        maturities = [m for m in MATURITY_ORDER if m in query.maturities and m.value in allowed]
        if not maturities:
            self.last_warnings.append(
                f"no maturity left: requested {[m.value for m in query.maturities]}, "
                f"allowed by settings {sorted(allowed)}"
            )
            return []
        products = self._products(query.product_types or self._s.nisar_product_list)
        cap = min(query.max_results, self._s.max_granules_per_request)
        out: list[GranuleRecord] = []
        attempted = failed = 0
        for maturity in maturities:
            for product in products:
                if len(out) >= cap:
                    break
                sn = short_name(product, maturity)
                attempted += 1
                try:
                    raw = cmr.find_granules(
                        sn, version=VERSION, aoi=query.aoi, start=query.start, end=query.end, limit=cap
                    )
                except ProviderError as exc:
                    failed += 1
                    self.last_warnings.append(str(exc))
                    continue
                for g in raw:
                    rec = granule_from_umm(g["umm"], g["meta"], short_name_=sn)
                    # CMR spatial matching is a superset; keep only real intersections
                    if rec.footprint is None or not rec.footprint.intersects(query.aoi.geometry):
                        continue
                    out.append(rec)
                    if len(out) >= cap:
                        break
        if attempted and failed == attempted:
            if self._fallback is not None:
                warnings = list(self.last_warnings)
                out = self._fallback.search_granules(query)
                self.last_warnings = warnings + ["CMR search failed; results come from the ASF fallback"] + [
                    f"ASF: {w}" for w in self._fallback.last_warnings
                ]
                return out
            raise ProviderError("; ".join(self.last_warnings))
        return out

    def get_granule_metadata(self, granule_id: str) -> GranuleRecord | None:
        self.last_warnings = []
        token = next((p for p in _LEVEL if f"_{p}_" in granule_id), None)
        products = [token] if token else self._products(list(_LEVEL))
        failed = attempted = 0
        for maturity in MATURITY_ORDER:
            for product in products:
                sn = short_name(product, maturity)
                attempted += 1
                try:
                    hits = cmr.find_granules(sn, version=VERSION, limit=1, granule_ur=granule_id)
                except ProviderError as exc:
                    failed += 1
                    self.last_warnings.append(str(exc))
                    continue
                if hits:
                    return granule_from_umm(hits[0]["umm"], hits[0]["meta"], short_name_=sn)
        if failed == attempted:
            raise ProviderError("; ".join(self.last_warnings))
        return None

    # ---- download ------------------------------------------------------------------------
    def download_granule(
        self,
        granule: GranuleRecord,
        dest_dir: Path | None,
        *,
        progress: ProgressCallback | None = None,
    ) -> Path:
        if not granule.download_url:
            raise DownloadError(f"{granule.granule_id} has no download URL", retryable=False)
        if granule.file_size_bytes and granule.file_size_bytes > self._s.max_file_size_bytes:
            raise DownloadError(
                f"{granule.granule_id} is {granule.file_size_bytes} bytes; the limit is "
                f"{self._s.max_file_size_bytes} (max_file_size_bytes)",
                retryable=False,
            )
        if self._dm is None:
            raise DownloadError("no download manager configured", retryable=False)
        filename = Path(urlparse(granule.download_url).path).name or f"{granule.granule_id}.h5"
        dest = (
            Path(dest_dir) / filename if dest_dir else storage.target_path(self._s.data_root, granule, filename)
        )
        session = self._auth.get_session()  # AuthenticationError propagates
        self._dm.download(
            granule.download_url,
            dest,
            expected_size=granule.file_size_bytes,
            checksum=granule.checksum,
            checksum_algorithm=granule.checksum_algorithm,
            progress=progress,
            session=session,
        )
        return dest
