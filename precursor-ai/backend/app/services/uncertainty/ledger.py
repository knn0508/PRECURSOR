"""Uncertainty ledger: turns metadata that Phases 2-6 already record into a per-area `UncertaintyReport`.

Only facts present in the inputs are reported. Nothing is estimated here. Each rule is deterministic and documented in
docs/scientific/UNCERTAINTY_AND_RELIABILITY.md.
"""
import uuid
from typing import Any

from app.schemas.uncertainty import SuppressionReason, UncertaintyItem, UncertaintyReport
from app.services.insar.phase_to_displacement import SIGN_CONVENTION_VERIFIED

# Nominal native resolutions (m) of datasets the project reads, from the dataset docs: NASADEM 1 arc-second (~30 m),
# ESA WorldCover 10 m, SoilGrids 250 m, SMAP SPL3SMP_E 9 km, IMERG 0.1 degree (~11 km at the equator). Nominal only.
NOMINAL_RESOLUTION_M = {"ELEVATION": 30.0, "LAND_COVER": 10.0, "SOIL": 250.0, "SMAP_SOIL_MOISTURE": 9000.0, "RAINFALL": 11000.0}
RESOLUTION_RATIO_FLAG = 2.0  # flag layers at least this many times coarser than the analysis grid


def build_report(area_id: uuid.UUID, features_manifest: dict[str, Any], *, insar_quality: dict[str, Any] | None = None,
                 series_quality: dict[str, dict[str, int]] | None = None) -> UncertaintyReport:
    items: list[UncertaintyItem] = []
    add = lambda code, phase, sev, msg, value=None: items.append(UncertaintyItem(code=code, source_phase=phase, severity=sev, message=msg, value=value))  # noqa: E731

    if features_manifest.get("contains_synthetic_data"):
        add("SYNTHETIC_INPUTS", 5, "LIMITATION", "Inputs include SYNTHETIC data: nothing derived from them describes the real world.")
    if features_manifest.get("real_data_validation") != "PERFORMED":
        add("REAL_DATA_NOT_VALIDATED", 5, "LIMITATION", "No real-data validation has been performed for the feature stack.")
    n_na = int((features_manifest.get("counts") or {}).get("not_available", 0))
    if n_na:
        add("FEATURES_NOT_AVAILABLE", 5, "WARNING", f"{n_na} feature(s) are NOT_AVAILABLE and would be missing model inputs.", float(n_na))
    for sk in features_manifest.get("skipped_layers") or []:
        add("LAYER_SKIPPED", 4, "WARNING", f"Layer {sk.get('layer')} was skipped: {sk.get('reason')}.")

    grid_res = (features_manifest.get("grid") or {}).get("resolution_m")
    if grid_res:
        for layer in features_manifest.get("input_layers") or []:
            native = NOMINAL_RESOLUTION_M.get(str(layer.get("layer_type")))
            if native and native / grid_res >= RESOLUTION_RATIO_FLAG:
                add("RESOLUTION_MISMATCH", 4, "WARNING",
                    f"{layer['layer_type']} is nominally {native:g} m, coarser than the {grid_res:g} m grid: values are shared across cells.", native / grid_res)
    for name, q in (series_quality or {}).items():
        exp, miss = q.get("expected_days", 0), q.get("missing_days", 0)
        if exp > 0 and miss > 0:
            add("TEMPORAL_GAPS", 4, "WARNING", f"{name}: {miss} of {exp} days missing (never filled).", 100.0 * miss / exp)

    if insar_quality is not None:
        if not insar_quality.get("sign_convention_verified", SIGN_CONVENTION_VERIFIED):
            add("SIGN_CONVENTION_UNVERIFIED", 3, "LIMITATION", "InSAR LOS sign convention is an unverified assumption.")
        if insar_quality.get("data_origin") == "SYNTHETIC_FIXTURE":
            add("INSAR_SYNTHETIC", 3, "LIMITATION", "InSAR input is a synthetic fixture.")
        coh = insar_quality.get("coherence") or {}
        if coh.get("mean") is not None:
            add("INSAR_COHERENCE_MEAN", 3, "INFO", "Mean coherence of the product (decorrelation lowers LOS precision).", float(coh["mean"]))
    return UncertaintyReport(
        area_id=area_id, items=items,
        notes=["Data-quality facts only. Predictive uncertainty is NOT_ESTIMATED: no model and no real method exists.",
               "Absent items mean 'not recorded in the inputs', not 'no problem'."])


def apply_suppression(report: UncertaintyReport, reasons: list[SuppressionReason]) -> UncertaintyReport:
    return report.model_copy(update={"suppressed": bool(reasons), "suppression_reasons": reasons})
