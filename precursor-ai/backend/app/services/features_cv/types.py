"""Shared vocabulary for Phase 5 (feature extraction and labelled sample dataset). Pure data; no I/O.

Scientific rules encoded here (see ADR-0007):
* Features are DESCRIPTIVE numbers from rasters. Nothing in this package scores, classifies or predicts.
* Missing is NaN / null, never zero. A feature that cannot be computed is NOT_AVAILABLE with a reason.
* Every artifact records a schema version, a code version and whether any input was synthetic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Semantic versions. A new feature is MINOR; a changed definition, unit or name is MAJOR.
FEATURE_SCHEMA_VERSION = "1.0.0"
DATASET_SCHEMA_VERSION = "1.0.0"
CODE_VERSION = "features_cv/1.0.0"  # no git repository exists yet, so the code version is stated, not derived

SYNTHETIC_ORIGIN = "SYNTHETIC_FIXTURE"  # same label Phase 3/4 use
REAL_ORIGIN = "REAL_SATELLITE"

# Words that must never appear in a field/column/key name produced by this package (ML boundary, ADR-0002/0007).
FORBIDDEN_NAME_TOKENS = ("risk", "probab", "susceptib", "predict", "score", "hazard", "danger", "unstable", "forecast")

_SCORE_LIKE = re.compile("|".join(FORBIDDEN_NAME_TOKENS), re.IGNORECASE)


class FeatureError(Exception):
    """A check failed; the operation must stop and say why."""


class NotAvailable(Exception):
    """An input does not exist. The step is reported NOT_AVAILABLE; nothing is filled in."""


class ChangeDetectionRefused(FeatureError):
    """Change features need two dated REAL inputs on the same grid; anything else is refused."""


class OptionalDependencyMissing(FeatureError):
    """An optional dependency (e.g. torch) is not installed. It is never installed by this project."""


def forbidden_names(names: list[str] | set[str]) -> list[str]:
    """Names (field, column, key) that look like a score/prediction. Used by the ML-boundary test and by the writers."""
    return sorted(n for n in names if _SCORE_LIKE.search(str(n)))


@dataclass
class FeatureSpec:
    """One feature as the schema defines it. `window_px` x resolution = `scale_m` (both recorded)."""

    name: str
    group: str  # terrain | texture | change
    description: str
    units: str  # "" for dimensionless
    dimension: str = "2d_raster"
    window_px: int | None = None
    scale_m: float | None = None
    source_layers: list[str] = field(default_factory=list)  # Phase 4 layer types (e.g. ELEVATION)
    temporal_kind: str = "static"
    requires_dated_real_inputs: bool = False
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}
