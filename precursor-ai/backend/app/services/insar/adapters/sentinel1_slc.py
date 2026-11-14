"""Sentinel1SLCAdapter: provider-independent interface for Sentinel-1 SLC (SAFE) inputs.

Strategy decision: a full TOPS pipeline (burst handling, back-geocoding, interferogram, filtering, unwrapping,
geocoding) is delegated to an established tool, never re-implemented. Options evaluated:
  * ESA SNAP (gpt graph)   - GUI/graph based, large Java install, good Sentinel-1 TOPS support.
  * ISCE2/ISCE3 (topsApp)  - script driven, heavy native build, strong for research workflows.
  * MintPy                 - time-series stage on top of existing interferograms (Phase 6 territory), not an SLC processor.
None is installed in this environment, so only INSPECTION (from the SAFE name and archive listing) is available.
`process` raises BlockedMissingInput: the workflow graphs/configs are not implemented in Phase 3.
"""
from __future__ import annotations

import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from app.services.insar.adapters.base import STAGE_INSPECT, ProductAdapter
from app.services.insar.external import ISCE, SNAP_GPT, SNAPHU
from app.services.insar.types import BlockedMissingInput, DataOrigin, InspectionReport, ProductKind

# S1A_IW_SLC__1SDV_20240101T120000_20240101T120027_051234_063ABC_1234.zip
_NAME = re.compile(
    r"^(?P<sat>S1[ABC])_(?P<mode>IW|EW|SM)_SLC__1S(?P<cls>[SD])(?P<pol>[HV])_"
    r"(?P<start>\d{8}T\d{6})_(?P<stop>\d{8}T\d{6})_(?P<orbit>\d{6})_"
)


class Sentinel1SLCAdapter(ProductAdapter):
    kind = ProductKind.S1_SLC

    @staticmethod
    def matches(path: Path) -> bool:
        return _NAME.match(path.name) is not None

    def inspect(self, path: Path, origin: DataOrigin) -> InspectionReport:
        stem = path.name
        m = _NAME.match(stem)
        is_zip = path.suffix.lower() == ".zip"
        size = path.stat().st_size if path.is_file() else 0
        rep = InspectionReport(file_name=path.name, file_size_bytes=size, file_format="zip" if is_zip else "safe",
                               product_kind=self.kind, data_origin=origin)
        if not m:
            rep.warnings.append("file name does not follow the Sentinel-1 SLC naming convention")
        else:
            rep.reference_time = datetime.strptime(m["start"], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
            rep.metadata.update(mission=m["sat"], mode=m["mode"], product_class=m["cls"], polarisation_code=m["pol"], absolute_orbit=int(m["orbit"]))
        if is_zip:
            try:
                with zipfile.ZipFile(path) as z:
                    names = z.namelist()
                rep.metadata["has_manifest"] = any(n.endswith("manifest.safe") for n in names)
                rep.metadata["measurement_files"] = sum(1 for n in names if "/measurement/" in n and n.endswith(".tiff"))
                if not rep.metadata["has_manifest"]:
                    rep.missing.append("manifest.safe")
            except zipfile.BadZipFile:
                rep.warnings.append("not a readable zip archive")
        rep.metadata["tools"] = self.tool_status()
        rep.supported_stages = [STAGE_INSPECT]
        rep.displacement_supported = False
        rep.displacement_blockers = [
            "Sentinel-1 SLC needs a TOPS interferometric workflow with an external tool (SNAP or ISCE) plus "
            "SNAPHU unwrapping; the workflow templates are not implemented in Phase 3.",
            *(f"tool not found: {n}" for n, ok in rep.metadata["tools"].items() if not ok),
        ]
        rep.warnings.append("precise orbit files must be supplied separately; none are fetched automatically")
        return rep

    @staticmethod
    def tool_status() -> dict[str, bool]:
        return {t.name: t.available() for t in (SNAP_GPT, ISCE, SNAPHU)}

    def process(self, *_args, **_kwargs):
        have = [n for n, ok in self.tool_status().items() if ok]
        raise BlockedMissingInput(
            "Sentinel-1 SLC processing is not available: required tools missing or workflows not implemented"
            + (f" (detected: {', '.join(have)})" if have else " (no SNAP/ISCE/SNAPHU detected)")
        )
