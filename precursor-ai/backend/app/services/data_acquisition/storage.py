"""On-disk layout for raw source data. Raw files are never overwritten silently."""
from __future__ import annotations

import re
from pathlib import Path

from app.services.data_acquisition.types import GranuleRecord, ProviderName

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(value: str) -> str:
    return _SAFE.sub("_", value).strip("._") or "unnamed"


def provider_dir(root: Path, granule: GranuleRecord) -> Path:
    """data/raw/nisar/gunw, data/raw/nasadem, data/raw/gpm/imerg, data/raw/smap, ..."""
    raw = root / "raw"
    match granule.provider:
        case ProviderName.NISAR:
            return raw / "nisar" / granule.product_type.lower()
        case ProviderName.NASADEM:
            return raw / "nasadem"
        case ProviderName.GPM:
            return raw / "gpm" / "imerg"
        case ProviderName.SMAP:
            return raw / "smap"
        case ProviderName.LANDSLIDE_CATALOG:
            return raw / "landslide_catalog"
    raise ValueError(f"unknown provider {granule.provider}")


def target_path(root: Path, granule: GranuleRecord, filename: str) -> Path:
    """<dir>/<YYYYMMDD>_<granule_id-or-filename>; version is part of the granule/collection id."""
    date = granule.acquisition_start.strftime("%Y%m%d") if granule.acquisition_start else "undated"
    return provider_dir(root, granule) / f"{date}__{safe_name(filename)}"


def metadata_dir(root: Path, kind: str) -> Path:
    """kind: collections | acquisitions | manifests"""
    return root / "metadata" / kind


def ensure_layout(root: Path) -> None:
    for sub in (
        "raw/nisar/gunw", "raw/nisar/gcov", "raw/nisar/gslc", "raw/nisar/goff", "raw/nisar/sme2",
        "raw/nasadem", "raw/gpm/imerg", "raw/smap", "raw/landslide_catalog",
        "metadata/collections", "metadata/acquisitions", "metadata/manifests", "processed", "samples", "aoi",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)
