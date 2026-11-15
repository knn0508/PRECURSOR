"""ModelRegistry: reads models/<model_id>/<version>/metadata.json and refuses incomplete models.

It reads metadata only. It never loads weights. A runtime predictor is attached separately with `attach` (the future,
separately authorized integration step); with none attached the service answers MODEL_NOT_TRAINED.
"""
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.prediction import ModelRegistryEntry, RefusedModel, ValidTime
from app.services.features_cv.schema import ModelInputSpec
from app.services.features_cv.types import FeatureError
from app.services.prediction.predictor import Predictor

METADATA_SCHEMA_VERSION = "1"
REQUIRED = ("model_id", "version", "heads", "model_card", "training_data_provenance", "valid_region", "valid_time", "input_spec")


class RegistryError(Exception):
    pass


def _entry_from_metadata(version_dir: Path, meta: dict[str, Any]) -> ModelRegistryEntry:
    missing = [k for k in REQUIRED if not meta.get(k)]
    if missing:
        raise RegistryError(f"metadata.json lacks required fields: {missing}")
    if meta["model_id"] != version_dir.parent.name or str(meta["version"]) != version_dir.name:
        raise RegistryError("metadata model_id/version do not match the folder names")
    card = (version_dir / str(meta["model_card"])).resolve()
    if version_dir.resolve() not in card.parents or not card.is_file():
        raise RegistryError("model card is missing (must be a file inside the version folder)")
    try:
        ModelInputSpec(**meta["input_spec"])  # builds the EXISTING Phase 5 contract; no second input schema
        valid_time = ValidTime.model_validate(meta["valid_time"])
        return ModelRegistryEntry(
            model_id=meta["model_id"], version=str(meta["version"]), heads=meta["heads"], model_card=str(meta["model_card"]),
            training_data_provenance=meta["training_data_provenance"], valid_region=meta["valid_region"], valid_time=valid_time,
            input_spec=meta["input_spec"], metadata_schema_version=str(meta.get("metadata_schema_version", METADATA_SCHEMA_VERSION)))
    except (FeatureError, TypeError, ValidationError) as exc:
        raise RegistryError(f"invalid metadata: {exc}") from exc


class ModelRegistry:
    def __init__(self, models_dir: Path):
        self.models_dir = Path(models_dir)
        self.entries: list[ModelRegistryEntry] = []
        self.refused: list[RefusedModel] = []
        self._predictors: dict[tuple[str, str], Predictor] = {}
        self.explainer_specs: dict[tuple[str, str], dict[str, Any]] = {}  # from explainer.json (declaration only)
        self._explainers: dict[tuple[str, str], Any] = {}
        self.scan()

    def scan(self) -> None:
        self.entries, self.refused, self.explainer_specs = [], [], {}
        if not self.models_dir.is_dir():
            return
        for meta_path in sorted(self.models_dir.glob("*/*/metadata.json")):
            version_dir = meta_path.parent
            if version_dir.parent.name.startswith("_"):  # _template and similar
                continue
            rel = meta_path.relative_to(self.models_dir).as_posix()
            try:
                entry = _entry_from_metadata(version_dir, json.loads(meta_path.read_text(encoding="utf-8")))
            except (RegistryError, json.JSONDecodeError, OSError) as exc:
                self.refused.append(RefusedModel(path=rel, reason=str(exc)))
                continue
            self.entries.append(entry)
            self._load_explainer_spec(version_dir, entry)

    def _load_explainer_spec(self, version_dir: Path, entry: ModelRegistryEntry) -> None:
        """Optional explainer.json: {method, background_dataset_ref, scopes}. A bad file refuses the explainer, not the model."""
        p = version_dir / "explainer.json"
        if not p.is_file():
            return
        rel = p.relative_to(self.models_dir).as_posix()
        try:
            spec = json.loads(p.read_text(encoding="utf-8"))
            missing = [k for k in ("method", "background_dataset_ref", "scopes") if not spec.get(k)]
            if missing or not set(spec["scopes"]) <= {"global", "local"}:
                raise RegistryError(f"explainer.json needs method, background_dataset_ref, scopes in (global, local); missing {missing}")
            self.explainer_specs[(entry.model_id, entry.version)] = spec
        except (RegistryError, json.JSONDecodeError, OSError, TypeError) as exc:
            self.refused.append(RefusedModel(path=rel, reason=str(exc)))

    def attach_explainer(self, model_id: str, version: str, explainer: Any) -> None:
        if (model_id, version) not in self.explainer_specs:
            raise RegistryError(f"{model_id}/{version} has no valid explainer.json")
        self._explainers[(model_id, version)] = explainer

    def find_explainer(self, head: str) -> tuple[ModelRegistryEntry, dict[str, Any], Any] | None:
        for e in self.entries:
            x = self._explainers.get((e.model_id, e.version))
            if x is not None and head in e.heads:
                return e, self.explainer_specs[(e.model_id, e.version)], x
        return None

    def attach(self, model_id: str, version: str, predictor: Predictor) -> None:
        """Bind a runtime predictor to a registered entry. Refuses unknown entries."""
        if self.get(model_id, version) is None:
            raise RegistryError(f"{model_id}/{version} is not a registered model")
        self._predictors[(model_id, version)] = predictor

    def get(self, model_id: str, version: str) -> ModelRegistryEntry | None:
        return next((e for e in self.entries if e.model_id == model_id and e.version == version), None)

    def find_predictor(self, head: str) -> tuple[ModelRegistryEntry, Predictor] | None:
        for e in self.entries:
            p = self._predictors.get((e.model_id, e.version))
            if p is not None and head in e.heads:
                return e, p
        return None
