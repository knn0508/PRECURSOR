"""InSAR integration: reference Phase 3 deformation products and summarise ELIGIBLE ones.

Rules (Phase 3 baseline: SYNTHETIC_PIPELINE_VERIFIED, REAL_DATA_VALIDATION NOT_PERFORMED):
* Products are referenced, never copied or reinterpreted.
* Only products with data_origin == REAL_SATELLITE can feed features. SYNTHETIC_FIXTURE and LOCAL_UNVERIFIED products are
  listed (labelled) but excluded, so synthetic data can never become "real environmental evidence".
* Even eligible products stay `scientifically_validated=False` and carry the unverified-sign-convention note.
* No products at all is a normal state: the group is NOT_AVAILABLE, never zero.
"""
from __future__ import annotations

from typing import Any

from app.services.environmental.types import DataOrigin

_UNITS = {"LOS_DISPLACEMENT": "mm", "LOS_VELOCITY": "mm/year", "COHERENCE": "dimensionless"}
_EXCLUDE_REASON = {
    DataOrigin.SYNTHETIC_FIXTURE.value: "synthetic test data: excluded from environmental features",
    DataOrigin.LOCAL_UNVERIFIED.value: "provenance unverified: excluded from environmental features",
}
NOTES = [
    "LOS (line-of-sight) measurement relative to an unspecified reference; not 3D motion.",
    "Phase sign convention is unverified; real-data validation of the InSAR pipeline has NOT been performed.",
    "A deformation product is a measurement, not a landslide risk map or prediction.",
]


def insar_features(products: list[dict[str, Any]]) -> dict[str, Any]:
    """`products`: plain dicts with product_type, data_origin, units, statistics, reference_time, secondary_time,
    scientifically_validated, id. Returns {status, values, units, warnings, included, excluded}."""
    included, excluded = [], []
    for p in products:
        origin = p.get("data_origin")
        if origin == DataOrigin.REAL_SATELLITE.value:
            included.append(p)
        else:
            excluded.append({"id": str(p.get("id")), "product_type": p.get("product_type"), "data_origin": origin,
                             "reason": _EXCLUDE_REASON.get(origin, "origin not eligible")})
    warnings = list(NOTES)
    if excluded:
        warnings.append(f"{len(excluded)} product(s) excluded by provenance (synthetic or unverified).")
    if not included:
        return {"status": "NOT_AVAILABLE", "values": {}, "units": {}, "warnings": warnings, "included": [], "excluded": excluded,
                "reason": "no eligible (real-satellite) InSAR products for this area"}
    values: dict[str, Any] = {"products": []}
    units: dict[str, str] = {}
    for p in included:
        st = p.get("statistics") or {}
        kind = p["product_type"]
        entry = {
            "id": str(p["id"]), "product_type": kind, "units": p.get("units") or _UNITS.get(kind),
            "mean": st.get("mean"), "min": st.get("min"), "max": st.get("max"), "std": st.get("std"),
            "valid_pixels": st.get("valid_pixels"), "nodata_percent": st.get("nodata_percent"),
            "reference_time": _iso(p.get("reference_time")), "secondary_time": _iso(p.get("secondary_time")),
            "scientifically_validated": bool(p.get("scientifically_validated", False)),
        }
        values["products"].append(entry)
        units[f"{kind.lower()}"] = entry["units"] or ""
    return {"status": "PROCESSED", "values": values, "units": units, "warnings": warnings, "included": [str(p["id"]) for p in included],
            "excluded": excluded}


def _iso(v: Any) -> str | None:
    return v.isoformat() if hasattr(v, "isoformat") else (v if isinstance(v, str) else None)
