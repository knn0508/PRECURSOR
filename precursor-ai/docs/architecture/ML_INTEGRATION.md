# ML integration: how a future model plugs in

Implemented in Phase 7 ([ADR-0008](../adr/ADR-0008-ml-slot-and-labelled-mock-frontend.md)). Design background: [PREDICTION_DESIGN](../scientific/PREDICTION_DESIGN.md). **No model exists.** Adding one needs a separately authorized stage (gate in PREDICTION_DESIGN section 8).

## Moving parts
| Piece | Where |
|---|---|
| Input contract (single, Phase 5) | `services/features_cv/schema.py` `ModelInputSpec` and `validate_against` |
| Schemas | `app/schemas/prediction.py`: `RiskModelInput` (wraps a `ModelInputSpec` dict), `RiskModelOutput`, `ModelRegistryEntry`, `PredictionResponse` |
| `Predictor` protocol, `NullPredictor` | `services/prediction/predictor.py` |
| `ModelRegistry` (metadata only, never loads weights) | `services/prediction/registry.py` |
| `PredictionService` (decides MODEL_NOT_TRAINED vs answer) | `services/prediction/service.py` |
| Endpoints | `/api/v1/prediction/status`, `/models`, `POST /susceptibility`, `POST /trigger` |
| Config | `PREDICTION_BACKEND` = `none` (default) or `registered_model`; `MODELS_DIR` (default `./models`) |
| Artifact folder | `models/<model_id>/<version>/` (README and `_template/` only; no weights) |

## Explainer (Phase 8)
Optional `explainer.json` next to `metadata.json`: `{"method", "background_dataset_ref", "scopes": ["global", "local"]}`. A malformed file is listed under `/models` -> `refused` (the model itself stays registered). Attach a runtime object implementing `Explainer.explain(model_input, features_manifest, scope, cell) -> Explanation` with `ModelRegistry.attach_explainer`. `POST /prediction/explain` returns `MODEL_NOT_AVAILABLE` until one is attached; an unsupported scope or incompatible data gives 422. Quality/uncertainty side: [UNCERTAINTY_AND_RELIABILITY](../scientific/UNCERTAINTY_AND_RELIABILITY.md).

## Frontend (Phase 9, implemented)
The workspace reads `POST /prediction/{head}`. `MODEL_NOT_TRAINED` gives the N/A view, or the labelled MOCK view when the build has `NEXT_PUBLIC_USE_MOCK_PREDICTIONS=true`. A response with `status: OK` and an `output` switches the same components to the real view (probability and class, calibration statement, valid region/time, uncertainty, explanation from `POST /prediction/explain`, model-card path) with no flag and no code change; the mock fixture module is never used for a real response. See `frontend/components/workspace/early-warning-panel.tsx`.

## Behaviour today
Under `none` every prediction route returns HTTP 200 with `{"status": "MODEL_NOT_TRAINED", "output": null, ...}`; the status route says the same. Under `registered_model` with no attached predictor the answer is identical.

## How to add a model (future stage)
1. Create `models/<model_id>/<version>/` (folder names equal `model_id` and `version`). Copy `_template/0.0.0/metadata.template.json` to `metadata.json`.
2. Required in `metadata.json`: `model_id`, `version`, `heads` (`susceptibility` and/or `trigger`), `model_card` (a file in the folder), `training_data_provenance`, `valid_region`, `valid_time`, `input_spec` (a `ModelInputSpec` dict: feature names from the Phase 5 schema, schema version, grid CRS/resolution). The registry **refuses** (and lists under `/models` -> `refused`) any model missing one of these, with a mismatching folder name, or whose feature names look score-like.
3. Weights stay out of git (`models/checkpoints/*` is ignored) and out of the response.
4. Attach a runtime predictor object implementing `Predictor.predict(RiskModelInput, features_manifest) -> RiskModelOutput` with `ModelRegistry.attach(model_id, version, predictor)` (wire this at app start in the authorized stage). The service calls `ModelInputSpec.validate_against(area features manifest)` before every call: major schema mismatch, missing/non-DONE feature, or different grid CRS/resolution gives HTTP 422 (no silent resampling).
5. Set `PREDICTION_BACKEND=registered_model` and restart.

## Schema versioning
Features: Phase 5 `FEATURE_SCHEMA_VERSION` (MAJOR must match). Registry metadata: `metadata_schema_version` (currently 1). The route/response schemas do not change when a model is enabled; only `status` and `output` do.

## Validation checklist before enabling
Real dated inventory; real Phase 4-6 features; validation per PREDICTION_DESIGN section 7 recorded in the model card (spatial-block CV, temporal hold-out, logistic and rainfall-only baselines, PR-AUC, recall at fixed false-alarm rate, Brier, calibration curve); calibration method stated before `risk_class` is filled; `valid_region`/`valid_time` set; Phase 9 UI labels reviewed.

## Frontend flip (Phase 9)
The UI reads `/prediction/status`. While it says `MODEL_NOT_TRAINED` it shows "N/A until a real, validated source exists" (or the labelled MOCK view when the default-off flag is on; mock data lives in the frontend only). When it says `OK` the same components render the real response; nothing else changes.

## Tests
`backend/tests/prediction/`: default backend, MODEL_NOT_TRAINED on every route, null predictor, registry accept/refuse cases, schema validation, a swap-path test with a **test-only `TestDouble`** (constant output, lives under `tests/`, never importable from app code), and a boundary scan (no score-like field names, no `TEST_DOUBLE` in `app/`).
