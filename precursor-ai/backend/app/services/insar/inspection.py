"""Product inspection service: detect format and product type, then delegate to the matching adapter."""
from __future__ import annotations

from pathlib import Path

import h5py

from app.services.insar.adapters.base import ProductAdapter
from app.services.insar.adapters.nisar_gcov import NISARGCOVAdapter
from app.services.insar.adapters.nisar_gslc import NISARGSLCAdapter
from app.services.insar.adapters.nisar_gunw import NISARGUNWAdapter
from app.services.insar.adapters.sentinel1_slc import Sentinel1SLCAdapter
from app.services.insar.types import DataOrigin, InspectionReport, ProductKind

_ADAPTERS: dict[ProductKind, ProductAdapter] = {
    ProductKind.GUNW: NISARGUNWAdapter(),
    ProductKind.GSLC: NISARGSLCAdapter(),
    ProductKind.GCOV: NISARGCOVAdapter(),
    ProductKind.S1_SLC: Sentinel1SLCAdapter(),
}
_SPEC = {"GUNW": ProductKind.GUNW, "GSLC": ProductKind.GSLC, "GCOV": ProductKind.GCOV}


def get_adapter(kind: ProductKind) -> ProductAdapter:
    return _ADAPTERS[kind]


def detect_kind(path: Path) -> tuple[ProductKind, str]:
    """(kind, format). Reads group names only, never raster data."""
    if Sentinel1SLCAdapter.matches(path):
        return ProductKind.S1_SLC, "zip" if path.suffix.lower() == ".zip" else "safe"
    try:
        if h5py.is_hdf5(path):
            with h5py.File(path, "r") as f:
                lsar = f.get("science/LSAR")
                if lsar is not None:
                    found = [k for k in _SPEC if k in lsar]
                    if len(found) == 1:
                        return _SPEC[found[0]], "hdf5"
                return ProductKind.UNKNOWN, "hdf5"
    except OSError:
        pass
    return ProductKind.UNKNOWN, "unknown"


def inspect_product(path: Path, origin: DataOrigin = DataOrigin.LOCAL_UNVERIFIED) -> InspectionReport:
    """Inspect a local file. Raises FileNotFoundError if absent; an unsupported file yields an UNKNOWN report."""
    if not path.exists():
        raise FileNotFoundError(path.name)
    kind, fmt = detect_kind(path)
    if kind is ProductKind.UNKNOWN:
        return InspectionReport(
            file_name=path.name, file_size_bytes=path.stat().st_size if path.is_file() else 0, file_format=fmt,
            product_kind=kind, data_origin=origin,
            warnings=["unsupported or unrecognised product: expected NISAR GUNW/GSLC/GCOV HDF5 or Sentinel-1 SLC"],
            displacement_blockers=["unrecognised product"],
        )
    return _ADAPTERS[kind].inspect(path, origin)
