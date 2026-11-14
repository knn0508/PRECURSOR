"""NISARGSLCAdapter: geocoded single-look COMPLEX data. One GSLC is one date: it carries phase for a future
interferogram but is not a displacement measurement. Inspection and quality only."""
from __future__ import annotations

import h5py

from app.services.insar import hdf
from app.services.insar.adapters.base import STAGE_INSPECT, STAGE_QC, NISARHDF5Adapter
from app.services.insar.types import InspectionReport, ProductKind


class NISARGSLCAdapter(NISARHDF5Adapter):
    kind = ProductKind.GSLC
    group = "GSLC"

    def _specific(self, f: h5py.File, idx: dict, rep: InspectionReport) -> None:
        complex_layers: dict[str, str] = {}

        def visit(name: str, obj) -> None:
            if isinstance(obj, h5py.Dataset) and obj.ndim == 2 and hdf.is_complex_dtype(obj.dtype):
                complex_layers[hdf.polarization_of(name) or name.rsplit("/", 1)[-1]] = "/" + name

        f.visititems(visit)
        rep.metadata["complex_layers"] = complex_layers
        rep.metadata["polarizations"] = sorted(complex_layers)
        rep.roles = {f"complex_{k}": v for k, v in complex_layers.items()}
        if not complex_layers:
            rep.missing.append("complex-valued 2-D datasets")
            rep.warnings.append("no complex-valued raster found")
        else:
            first = complex_layers[sorted(complex_layers)[0]]
            rep.datasets.extend(self._info(f, p) for p in complex_layers.values())
            blockers: list[str] = []
            rep.grid = self._grid(f, first, rep, blockers)
            rep.warnings.extend(b for b in blockers)
            self._wavelength(f, idx, first, rep, [])
        t = hdf.parse_time(self._first(f, idx, "zeroDopplerStartTime"))
        if t:
            rep.reference_time = t
        rep.displacement_blockers = [
            "GSLC is a single-date complex product. Displacement needs a co-registered pair, an interferogram "
            "and phase unwrapping by an established external tool, none of which is wired or installed.",
        ]
        rep.displacement_supported = False
        rep.supported_stages = [STAGE_INSPECT, STAGE_QC]
        rep.warnings.append("phase is preserved in the file; no displacement is derived from GSLC alone")
