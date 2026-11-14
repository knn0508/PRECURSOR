"""NISARGUNWAdapter: geocoded UNWRAPPED interferogram. Already interferometrically processed, so it is never run
through an SLC interferogram pipeline again. Datasets are discovered by name; the layout is not assumed."""
from __future__ import annotations

import h5py

from app.services.insar import hdf
from app.services.insar.adapters.base import (
    STAGE_DISP, STAGE_INSPECT, STAGE_PRE, STAGE_QC, NISARHDF5Adapter,
)
from app.services.insar.types import InspectionReport, ProductKind


class NISARGUNWAdapter(NISARHDF5Adapter):
    kind = ProductKind.GUNW
    group = "GUNW"

    def _specific(self, f: h5py.File, idx: dict, rep: InspectionReport) -> None:
        blockers = rep.displacement_blockers
        phase_paths = sorted(idx.get("unwrappedPhase", []))
        if not phase_paths:
            rep.missing.append("unwrappedPhase")
            blockers.append("no 'unwrappedPhase' dataset found")
        layers: dict[str, dict[str, str | None]] = {}
        for p in phase_paths:
            pol = hdf.polarization_of(p) or "UNKNOWN"
            if pol in layers:
                rep.ambiguous.setdefault(f"unwrapped_phase:{pol}", [layers[pol]["unwrapped_phase"]]).append(p)
                continue
            layers[pol] = {
                "unwrapped_phase": p,
                "coherence": hdf.nearest(f, p, "coherenceMagnitude"),
                "connected_components": hdf.nearest(f, p, "connectedComponents"),
            }
        rep.metadata["layers"] = layers
        rep.metadata["polarizations"] = sorted(layers)
        if len(layers) > 1:
            rep.warnings.append(f"several polarizations found {sorted(layers)}: choose one explicitly")
        if rep.ambiguous:
            rep.warnings.append("multiple unwrappedPhase datasets share a polarization: first one used, others ignored")
        if layers:
            first = layers[sorted(layers)[0]]
            rep.roles = {k: v for k, v in first.items() if v}
            ph = f[first["unwrapped_phase"]]
            for role, path in rep.roles.items():
                rep.datasets.append(self._info(f, path))
            if first["coherence"] is None:
                rep.warnings.append("no coherenceMagnitude found next to unwrappedPhase: no coherence layer or mask")
            elif f[first["coherence"]].shape != ph.shape:
                rep.warnings.append("coherenceMagnitude shape differs from unwrappedPhase: coherence will not be used")
            units = hdf.units_of(ph)
            if units is None:
                rep.warnings.append("unwrappedPhase has no 'units' attribute: radians assumed (not verified)")
            elif "rad" not in units.lower():
                blockers.append(f"unwrappedPhase units are {units!r}, not radians")
            rep.grid = self._grid(f, first["unwrapped_phase"], rep, blockers)
            self._wavelength(f, idx, first["unwrapped_phase"], rep, blockers)
        if rep.reference_time is None or rep.secondary_time is None:
            rep.warnings.append("reference/secondary acquisition time missing: temporal baseline and velocity unavailable")
        pb = idx.get("perpendicularBaseline")
        if pb is None:
            rep.warnings.append("perpendicular baseline not found")
        else:
            rep.metadata["perpendicular_baseline_paths"] = pb[:3]
        rep.warnings.append(
            "phase sign convention and differential nature are NOT verified against the product specification"
        )
        rep.displacement_supported = not blockers
        rep.supported_stages = (
            [STAGE_INSPECT, STAGE_PRE, STAGE_DISP, STAGE_QC] if rep.displacement_supported else [STAGE_INSPECT, STAGE_QC]
        )
