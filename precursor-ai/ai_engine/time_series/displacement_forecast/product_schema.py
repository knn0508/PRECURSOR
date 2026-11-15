"""Three-layer per-pixel product record (skill v3, Phase 6). Research estimate, not a hazard warning.

Every rendered value states WHAT it is. Rules enforced here:
  * masked-but-finite or missing at the observation date -> status "sensor_limit", value None
  * a model output -> status "inferred" with a non-null uncertainty; never labelled "observed"
  * decomposed components carry their assumption (ZERO_NORTH / SLOPE_CONSTRAINED)
"""
from __future__ import annotations

STATUSES = {"observed", "inferred", "sensor_limit", "not_comparable"}
SOURCES = {"OPERA_S1_ASC", "OPERA_S1_DESC", "NISAR_GUNW", "FUSION", "NONE"}
QUANTITIES = {"LOS_DISPLACEMENT_MM", "LOS_VELOCITY_MM_PER_DAY", "CONDITIONAL_EAST_UP", "NONE"}
ASSUMPTIONS = {"NONE", "ZERO_NORTH", "SLOPE_CONSTRAINED", "OTHER_EXPLICIT"}


def record(status, source, quantity, value=None, uncertainty=None, start=None, end=None,
           quality_reason="", correction_status=None, assumption="NONE") -> dict:
    if status not in STATUSES or source not in SOURCES or quantity not in QUANTITIES or assumption not in ASSUMPTIONS:
        raise ValueError("invalid enum value")
    if status in ("sensor_limit", "not_comparable") and value is not None:
        raise ValueError(f"{status} must not carry a value")
    if status == "inferred" and (value is not None) and uncertainty is None:
        raise ValueError("inferred values need an uncertainty")
    if quantity == "CONDITIONAL_EAST_UP" and assumption == "NONE":
        raise ValueError("decomposed components must state their assumption")
    return {"status": status, "source": source, "observation_start": start, "observation_end": end,
            "quantity": quantity, "value": value, "uncertainty": uncertainty, "quality_reason": quality_reason,
            "correction_status": correction_status or {}, "assumption": assumption}


def from_observation(obs_class: str, source: str, value, start, end, correction_status=None) -> dict:
    """Map an observation class (geometry_alignment.obs_class) to a record; masked values are never shown."""
    if obs_class == "valid_observation":
        return record("observed", source, "LOS_DISPLACEMENT_MM", float(value), None, start, end, "valid_qa", correction_status)
    reason = "masked_cc0_or_low_coherence" if obs_class == "masked_but_finite" else "no_value"
    return record("sensor_limit", source, "NONE", None, None, start, end, reason, correction_status)
