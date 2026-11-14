"""ModelInputSpec: the feature contract a FUTURE model will be validated against (ML SLOT, Prompts.md header; Phase 7 owns
services/prediction/). Phase 5 only provides this schema and its compatibility check. It loads no model and scores nothing.

A model's spec is compatible with a feature manifest when the MAJOR feature-schema version matches and every feature the
spec names exists in the manifest with status DONE. The check is run at model-load time by the Phase 7 registry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.features_cv.types import (
    DATASET_SCHEMA_VERSION, FEATURE_SCHEMA_VERSION, FeatureError, forbidden_names)


def major(version: str) -> int:
    try:
        return int(str(version).split(".")[0])
    except ValueError:
        raise FeatureError(f"invalid schema version {version!r}") from None


@dataclass
class ModelInputSpec:
    feature_names: list[str]
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    dataset_schema_version: str = DATASET_SCHEMA_VERSION
    nodata_policy: str = "NaN"  # missing is NaN, never zero
    grid_crs: str | None = None
    grid_resolution_m: float | None = None
    normalisation: dict[str, Any] = field(default_factory=dict)  # feature -> Normalisation.to_dict()
    source_manifest_sha256: str | None = None
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.feature_names or len(set(self.feature_names)) != len(self.feature_names):
            raise FeatureError("feature_names must be non-empty and unique")
        bad = forbidden_names(self.feature_names)
        if bad:
            raise FeatureError(f"feature names look like scores/predictions: {bad}")

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    def validate_against(self, manifest: dict[str, Any]) -> None:
        """Raise FeatureError unless `manifest` (a features manifest.json) can feed this spec."""
        if major(manifest.get("feature_schema_version", "")) != major(self.feature_schema_version):
            raise FeatureError(f"feature schema major version differs: model {self.feature_schema_version}, "
                               f"data {manifest.get('feature_schema_version')}")
        done = {f["name"] for f in manifest.get("features", []) if f.get("status") == "DONE"}
        missing = [n for n in self.feature_names if n not in done]
        if missing:
            raise FeatureError(f"features required by the model are missing or not DONE: {missing}")
        if self.grid_crs and manifest.get("grid", {}).get("crs") != self.grid_crs:
            raise FeatureError("grid CRS differs from the model's expected CRS (no silent resampling)")
        if self.grid_resolution_m is not None and manifest.get("grid", {}).get("resolution_m") != self.grid_resolution_m:
            raise FeatureError("grid resolution differs from the model's expected resolution (no silent resampling)")
