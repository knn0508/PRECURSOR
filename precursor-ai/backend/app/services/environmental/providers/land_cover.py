"""Land cover provider: ESA WorldCover (primary) - proposal + local-file reader. NO network access, NO download.

Why WorldCover over MODIS MCD12Q1: 10 m vs 500 m, global, 3x3 deg COG tiles on AWS Open Data readable without credentials
(`--no-sign-request`), CC BY 4.0. MCD12Q1 needs an Earthdata login and is 500 m (alternative only; not implemented).
Verified: esa-worldcover.org/en/data-access (versions, tiles, s3 paths, licence) and the Earth Engine catalogue page for
the v200 legend/colours. NOT verified: tile file naming and per-tile size (assumed), raster nodata for the Map layer.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from app.services.environmental.providers.base import (
    AcquisitionProposal, EnvironmentalProvider, aoi_bounds, raster_covers,
)
from app.services.environmental.storage import external_dir
from app.services.environmental.types import NotAvailable

# Official ESA WorldCover legend (11 classes) with the documented colours.
WORLDCOVER_LEGEND: dict[int, tuple[str, str]] = {
    10: ("Tree cover", "#006400"), 20: ("Shrubland", "#ffbb22"), 30: ("Grassland", "#ffff4c"),
    40: ("Cropland", "#f096ff"), 50: ("Built-up", "#fa0000"), 60: ("Bare / sparse vegetation", "#b4b4b4"),
    70: ("Snow and ice", "#f0f0f0"), 80: ("Permanent water bodies", "#0064c8"), 90: ("Herbaceous wetland", "#0096a0"),
    95: ("Mangroves", "#00cf75"), 100: ("Moss and lichen", "#fae6a0"),
}
VERSIONS = {"v100": 2020, "v200": 2021}
URLS = ["https://esa-worldcover.org/en/data-access",
        "s3://esa-worldcover/v200/2021/map", "s3://esa-worldcover/v100/2020/map",
        "https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200"]
LICENCE = "CC BY 4.0 (ESA WorldCover Consortium; (C) ESA WorldCover project, contains modified Copernicus Sentinel data)"
TILE_DEG = 3
EST_TILE_MB = 150.0  # ASSUMPTION, unverified


def tile_count(bbox: tuple[float, float, float, float]) -> int:
    w, s, e, n = bbox
    nx = math.floor((e - 1e-12) / TILE_DEG) - math.floor(w / TILE_DEG) + 1
    ny = math.floor((n - 1e-12) / TILE_DEG) - math.floor(s / TILE_DEG) + 1
    return nx * ny


class LandCoverProvider(EnvironmentalProvider):
    name = "land_cover"

    def describe(self) -> dict[str, Any]:
        return {
            "provider": "WORLDCOVER", "dataset": "ESA WorldCover", "versions": VERSIONS, "resolution_m": 10,
            "tiles": "3x3 degree COG, EPSG:4326", "classes": {k: v[0] for k, v in WORLDCOVER_LEGEND.items()},
            "colours": {k: v[1] for k, v in WORLDCOVER_LEGEND.items()}, "licence": LICENCE, "source_urls": URLS,
            "auth_required": False, "alternative_not_implemented": "MODIS MCD12Q1 (500 m, Earthdata login)",
            "verified": ["versions/years", "resolution", "tile size", "AWS paths", "CC BY 4.0", "legend codes/names/colours (v200 EE page)"],
            "not_verified": ["tile file naming", "tile sizes", "Map nodata value"],
            "implementation_status": "IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA",
            "capabilities": "proposal + local GeoTIFF reader only; no download",
        }

    def plan_acquisition(self, aoi: Any, version: str = "v200", **_: Any) -> AcquisitionProposal:
        if version not in VERSIONS:
            raise ValueError(f"unknown WorldCover version {version!r}")
        bbox = aoi_bounds(aoi)
        n = tile_count(bbox)
        year = VERSIONS[version]
        return AcquisitionProposal(
            provider="WORLDCOVER", dataset="ESA WorldCover map", version=f"{version} ({year})",
            source_urls=[u for u in URLS if f"/{version}/" in u or u.startswith("https")], aoi_bbox=bbox,
            expected_file_count=n, estimated_size_mb=n * EST_TILE_MB,
            size_basis=f"ESTIMATE: {n} 3-degree tile(s) x assumed {EST_TILE_MB:.0f} MB; per-tile size NOT verified",
            requires_auth=False, auth_note="AWS Open Data bucket is public (--no-sign-request); Terrascope needs login.",
            intended_use="Categorical land-cover class distribution per AOI (descriptive).",
            destination="data/external/land_cover/", notes=[f"Licence: {LICENCE}", "Proposal only: nothing was downloaded."])

    def local_inputs(self, data_root: Path, aoi: Any) -> list[Path]:
        bbox = aoi_bounds(aoi)
        d = external_dir(data_root, "land_cover")
        return sorted(p for p in d.glob("*.tif") if raster_covers(p, bbox)) if d.is_dir() else []

    def read_local(self, files: list[Path], aoi: Any, **kw: Any):
        from app.services.environmental.land_cover.land_cover_processor import process_land_cover
        if not files:
            raise NotAvailable("no local land-cover files for the AOI")
        return process_land_cover(files, aoi, **kw)
