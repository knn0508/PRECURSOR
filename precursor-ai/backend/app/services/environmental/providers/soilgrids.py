"""SoilGrids 2.0 (ISRIC) provider: proposal + local-file reader. NO network access, NO download.

Verified from ISRIC docs (docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html): property table with mapped units and
conversion factors (divide the stored integer by the factor), six depth intervals, statistics layers.
NOT verified here: native CRS (Homolosine is expected; the reader never assumes it, it uses the file's CRS), nodata value
(the file's own nodata is used), REST/WCS rate limits.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from app.services.environmental.providers.base import (
    AcquisitionProposal, EnvironmentalProvider, aoi_bounds, raster_covers,
)
from app.services.environmental.storage import external_dir
from app.services.environmental.types import NotAvailable

# property -> (description, mapped units, conversion factor, conventional units). Source: ISRIC layers table.
SOILGRIDS_PROPERTIES: dict[str, tuple[str, str, int, str]] = {
    "bdod": ("Bulk density", "cg/cm3", 100, "kg/dm3"),
    "cec": ("CEC buffered at pH 7", "mmol(c)/kg", 10, "cmol(c)/kg"),
    "cfvo": ("Coarse fragments", "cm3/dm3 (vol permille)", 10, "cm3/100cm3 (vol%)"),
    "clay": ("Clay", "g/kg", 10, "g/100g (%)"),
    "nitrogen": ("Nitrogen", "cg/kg", 100, "g/kg"),
    "ocd": ("Organic carbon density", "hg/m3", 10, "kg/m3"),
    "ocs": ("Organic carbon stocks", "t/ha", 10, "kg/m2"),
    "phh2o": ("pH in water", "pH x 10", 10, "pH (unitless)"),
    "sand": ("Sand", "g/kg", 10, "g/100g (%)"),
    "silt": ("Silt", "g/kg", 10, "g/100g (%)"),
    "soc": ("Soil organic carbon", "dg/kg", 10, "g/kg"),
    "wv0010": ("Volumetric water content at 10 kPa", "1e-3 cm3/cm3", 10, "1e-2 cm3/cm3 (%)"),
    "wv0033": ("Volumetric water content at 33 kPa", "1e-3 cm3/cm3", 10, "1e-2 cm3/cm3 (%)"),
    "wv1500": ("Volumetric water content at 1500 kPa", "1e-3 cm3/cm3", 10, "1e-2 cm3/cm3 (%)"),
}
SOILGRIDS_DEPTHS_CM = ((0, 5), (5, 15), (15, 30), (30, 60), (60, 100), (100, 200))
SOILGRIDS_STATISTICS = ("mean", "Q0.05", "Q0.5", "Q0.95", "uncertainty")
# ISRIC: uncertainty = (Q0.95 - Q0.05) / Q0.50, stored x10 -> /10 gives a unitless ratio.
UNCERTAINTY_UNITS = ("(Q0.95-Q0.05)/Q0.50 x 10", 10, "ratio (unitless)")

# ISRIC file naming convention <property>_<top>-<bottom>cm_<statistic>[ _...].tif
FILE_RE = re.compile(r"^(?P<prop>[a-z0-9]+)_(?P<top>\d+)-(?P<bot>\d+)cm_(?P<stat>mean|Q0\.05|Q0\.5|Q0\.95|uncertainty)", re.I)

DOC_URLS = ["https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html",
            "https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs.html"]
LICENCE = "CC BY 4.0; cite Poggio et al. (2021) SoilGrids 2.0, SOIL 7, 217-240"


def parse_soil_filename(name: str) -> dict[str, Any] | None:
    m = FILE_RE.match(Path(name).name)
    if not m or m["prop"].lower() not in SOILGRIDS_PROPERTIES:
        return None
    stat = m["stat"]
    stat = "mean" if stat.lower() == "mean" else "uncertainty" if stat.lower() == "uncertainty" else "Q" + stat[1:]
    return {"property": m["prop"].lower(), "top_cm": int(m["top"]), "bottom_cm": int(m["bot"]), "statistic": stat}


def units_for(prop: str, statistic: str) -> tuple[str, int, str]:
    """(source units, scale factor, converted units) for a layer."""
    if statistic == "uncertainty":
        return UNCERTAINTY_UNITS
    _, src, factor, conv = SOILGRIDS_PROPERTIES[prop]
    return src, factor, conv


def convert(prop: str, statistic: str, raw: float) -> float:
    """mapped integer -> conventional units: raw / documented factor. The only conversion this module performs."""
    return float(raw) / units_for(prop, statistic)[1]


class SoilGridsProvider(EnvironmentalProvider):
    name = "soilgrids"

    def describe(self) -> dict[str, Any]:
        return {
            "provider": "SOILGRIDS", "dataset": "SoilGrids 250 m v2.0", "resolution_m": 250,
            "properties": {k: {"description": v[0], "mapped_units": v[1], "factor": v[2], "units": v[3]}
                           for k, v in SOILGRIDS_PROPERTIES.items()},
            "depth_intervals_cm": list(SOILGRIDS_DEPTHS_CM), "statistics": list(SOILGRIDS_STATISTICS),
            "licence": LICENCE, "source_urls": DOC_URLS, "auth_required": False,
            "verified": ["property table + factors", "depth intervals", "statistics", "CC BY 4.0"],
            "not_verified": ["native CRS (Homolosine expected)", "nodata value", "REST/WCS rate limits"],
            "implementation_status": "IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA",
            "capabilities": "proposal + local GeoTIFF reader only; no download, no REST/WCS client",
        }

    def plan_acquisition(self, aoi: Any, properties: tuple[str, ...] = ("clay", "sand", "silt", "soc", "phh2o", "bdod"),
                         depths: tuple[tuple[int, int], ...] = SOILGRIDS_DEPTHS_CM,
                         statistics: tuple[str, ...] = ("mean",), **_: Any) -> AcquisitionProposal:
        bbox = aoi_bounds(aoi)
        w, s, e, n = bbox
        n_layers = len(properties) * len(depths) * len(statistics)
        px = max((e - w) * 111_320 * math.cos(math.radians((s + n) / 2)) / 250, 1) * max((n - s) * 110_574 / 250, 1)
        return AcquisitionProposal(
            provider="SOILGRIDS", dataset="SoilGrids 250 m", version="2.0", source_urls=list(DOC_URLS), aoi_bbox=bbox,
            expected_file_count=n_layers, estimated_size_mb=round(px * 2 * n_layers / 1e6, 2),
            size_basis="ESTIMATE: AOI pixels at 250 m x 2 bytes (int16) x layers, uncompressed upper bound; one file per layer "
                       "if fetched as AOI subsets (WCS) - unverified",
            requires_auth=False, auth_note="No credentials documented for SoilGrids access (WebDAV/WCS/GEE per ISRIC docs).",
            intended_use="Descriptive soil property statistics per AOI (not a susceptibility input by itself).",
            destination="data/external/soilgrids/",
            notes=["Place files named <property>_<top>-<bottom>cm_<statistic>.tif.", f"Licence: {LICENCE}",
                   "Proposal only: nothing was downloaded."])

    def local_inputs(self, data_root: Path, aoi: Any) -> list[Path]:
        bbox = aoi_bounds(aoi)
        d = external_dir(data_root, "soilgrids")
        if not d.is_dir():
            return []
        return sorted(p for p in d.glob("*.tif") if parse_soil_filename(p.name) and raster_covers(p, bbox))

    def read_local(self, files: list[Path], aoi: Any, **kw: Any):
        from app.services.environmental.soil.soil_processor import process_soil
        if not files:
            raise NotAvailable("no local SoilGrids files for the AOI")
        return process_soil(files, aoi, **kw)
