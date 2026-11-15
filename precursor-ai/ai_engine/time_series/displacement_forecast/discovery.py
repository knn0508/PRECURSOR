"""Catalog discovery through NASA CMR (public search; no login required).

Search only. A granule appearing here is NOT proof it is usable: quality,
geometry and known issues are checked later on the actual files.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd
import requests

CMR = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"

COLLECTIONS = {
    "OPERA_L3_DISP-S1_V1": "opera_disp",
    "NISAR_L2_GUNW_V1": "nisar_gunw_validated",
    "NISAR_L2_GUNW_PROVISIONAL_V1": "nisar_gunw_provisional",
    "NISAR_L2_GCOV_V1": "nisar_gcov_validated",
    "NISAR_L2_GCOV_PROVISIONAL_V1": "nisar_gcov_provisional",
}


@dataclass
class AOI:
    name: str
    west: float
    south: float
    east: float
    north: float

    @property
    def bbox(self) -> str:
        return f"{self.west},{self.south},{self.east},{self.north}"

    @property
    def center(self) -> tuple[float, float]:
        return ((self.west + self.east) / 2, (self.south + self.north) / 2)


def _attr(umm: dict, name: str):
    for a in umm.get("AdditionalAttributes", []) or []:
        if a.get("Name", "").upper() == name.upper():
            v = a.get("Values") or []
            return v[0] if v else None
    return None


def _data_url(umm: dict, suffixes=(".nc", ".h5")) -> str | None:
    for u in umm.get("RelatedUrls", []) or []:
        url = u.get("URL", "")
        if u.get("Type") == "GET DATA" and url.startswith("https") and url.endswith(suffixes):
            return url
    return None


def search(short_name: str, aoi: AOI, temporal: tuple[str, str] | None = None,
           page_size: int = 500, max_pages: int = 20, timeout: int = 120) -> pd.DataFrame:
    """Exhaustively page CMR for one collection over the AOI bbox."""
    rows, headers = [], {}
    params = {"short_name": short_name, "bounding_box": aoi.bbox, "page_size": page_size}
    if temporal:
        params["temporal"] = f"{temporal[0]}T00:00:00Z,{temporal[1]}T23:59:59Z"
    total = None
    for _ in range(max_pages):
        r = requests.get(CMR, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        total = int(r.headers.get("CMR-Hits", 0))
        items = r.json().get("items", [])
        for it in items:
            umm, meta = it["umm"], it["meta"]
            gid = umm.get("GranuleUR", meta.get("native-id"))
            rng = (umm.get("TemporalExtent") or {}).get("RangeDateTime") or {}
            rows.append({
                "collection": short_name,
                "granule_id": gid,
                "concept_id": meta.get("concept-id"),
                "begin": rng.get("BeginningDateTime"),
                "end": rng.get("EndingDateTime"),
                "url": _data_url(umm),
                "size_mb": sum((f.get("Size") or 0) for f in
                               (umm.get("DataGranule") or {}).get("ArchiveAndDistributionInformation", [])
                               if (f.get("SizeUnit") or "MB") == "MB") or None,
                "orbit_direction": _attr(umm, "ASCENDING_DESCENDING") or _attr(umm, "ORBIT_DIRECTION"),
                "track": _attr(umm, "PATH_NUMBER") or _attr(umm, "TRACK_NUMBER") or _attr(umm, "RELATIVE_ORBIT"),
                "frame": _attr(umm, "FRAME_NUMBER") or _attr(umm, "FRAME"),
                "polarization": _attr(umm, "POLARIZATION"),
                "processing_level_version": umm.get("PGEVersionClass", {}).get("PGEVersion")
                if isinstance(umm.get("PGEVersionClass"), dict) else None,
            })
        sa = r.headers.get("CMR-Search-After")
        if not items or not sa or len(rows) >= total:
            break
        headers["CMR-Search-After"] = sa
    df = pd.DataFrame(rows)
    df.attrs["cmr_hits"] = total
    return df


_OPERA_RE = re.compile(r"_F(?P<frame>\d+)_(?P<pol>[A-Z]{2})_(?P<ref>\d{8}T\d{6}Z)_(?P<sec>\d{8}T\d{6}Z)_v(?P<ver>[\d.]+)_(?P<prod>\d{8}T\d{6}Z)")


def parse_opera_names(df: pd.DataFrame) -> pd.DataFrame:
    """Add frame / reference / secondary datetimes parsed from OPERA DISP-S1 granule names."""
    p = df["granule_id"].str.extract(_OPERA_RE)
    out = df.copy()
    out["frame"] = p["frame"]
    out["polarization"] = p["pol"]
    out["reference_dt"] = pd.to_datetime(p["ref"], format="%Y%m%dT%H%M%SZ")
    out["secondary_dt"] = pd.to_datetime(p["sec"], format="%Y%m%dT%H%M%SZ")
    out["product_version"] = p["ver"]
    out["production_dt"] = pd.to_datetime(p["prod"], format="%Y%m%dT%H%M%SZ")
    return out


def dedupe_opera(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest production of each (frame, reference, secondary) pair."""
    return (df.sort_values("production_dt")
              .drop_duplicates(["frame", "reference_dt", "secondary_dt"], keep="last")
              .sort_values(["frame", "secondary_dt"]).reset_index(drop=True))


def maturity_from_collection(short_name: str) -> str:
    if "PROVISIONAL" in short_name:
        return "PROVISIONAL"
    if short_name.startswith("NISAR"):
        return "VALIDATED"
    return "OPERA_V1"
