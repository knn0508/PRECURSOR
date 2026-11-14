"""NISARGCOVAdapter: geocoded polarimetric COVARIANCE (backscatter statistics). It has no interferometric phase
and must never be used to derive displacement. Inspection and quality only."""
from __future__ import annotations

import re

import h5py

from app.services.insar import hdf
from app.services.insar.adapters.base import STAGE_INSPECT, STAGE_QC, NISARHDF5Adapter
from app.services.insar.types import InspectionReport, ProductKind

_COV_TERM = re.compile(r"^[HVRL]{4}$")  # HHHH, HVHV, HHVV ... covariance elements


class NISARGCOVAdapter(NISARHDF5Adapter):
    kind = ProductKind.GCOV
    group = "GCOV"

    def _specific(self, f: h5py.File, idx: dict, rep: InspectionReport) -> None:
        terms = {n: p[0] for n, p in idx.items() if _COV_TERM.match(n)}
        rep.metadata["covariance_terms"] = sorted(terms)
        rep.metadata["polarizations"] = sorted({t[:2] for t in terms} | {t[2:] for t in terms})
        rep.roles = {f"cov_{k}": v for k, v in terms.items()}
        if not terms:
            rep.missing.append("covariance terms (e.g. HHHH)")
            rep.warnings.append("no covariance datasets found")
        else:
            first = terms[sorted(terms)[0]]
            rep.datasets.extend(self._info(f, p) for p in terms.values())
            blockers: list[str] = []
            rep.grid = self._grid(f, first, rep, blockers)
            rep.warnings.extend(blockers)
            ds = f[first]
            rep.metadata["covariance_units"] = hdf.units_of(ds)
        t = hdf.parse_time(self._first(f, idx, "zeroDopplerStartTime"))
        if t:
            rep.reference_time = t
        rep.displacement_blockers = ["GCOV contains backscatter covariance, not interferometric phase: no displacement"]
        rep.displacement_supported = False
        rep.supported_stages = [STAGE_INSPECT, STAGE_QC]
