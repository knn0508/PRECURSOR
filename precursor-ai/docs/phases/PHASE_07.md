# Phase 7: Predictive Risk Assessment Engine (architecture and ML slot, no ML)

Status: **COMPLETED** (contracts and empty ML slot, 2026-11-15; see Implementation status). Roadmap: [ROADMAP](../project/ROADMAP.md). Executable brief: [Prompts.md](../../Prompts.md) (Phase 7).

## Objective
Define the landslide early-prediction **architecture** and reserve the **ML slot** where the user's finished model will be plugged in later without redesign. **No model is trained, loaded or run in this phase.**

## Scope
- Two model heads: **susceptibility** (static, per cell, "where") and **trigger / early warning** (dynamic, per cell and time, "when", with stated lead time and horizon). Analysis units (grid cell, time step) and target definitions (event within X days / Y metres) with label-quality caveats.
- ML slot: `backend/app/services/prediction/` with `Predictor` protocol, `NullPredictor`, `ModelRegistry` (reads `models/<model_id>/<version>/metadata.json`; refuses models lacking model card, provenance, valid region/time, or a feature spec that passes the **existing** Phase 5 `ModelInputSpec.validate_against`; no second input schema; `RiskModelInput` wraps `ModelInputSpec`); config `PREDICTION_BACKEND = none | registered_model` (default `none`); empty artifact folder with README and template only.
- Pydantic schemas and API: `RiskModelInput`, `RiskModelOutput` (probability, class, calibration info, uncertainty, model id/version, training provenance, valid region/time); `/api/v1/prediction/{status,models,susceptibility,trigger}` return `MODEL_NOT_TRAINED` under `none`.
- Swap-path contract test using a **test-only** dummy predictor (`TEST_DOUBLE`, lives under `tests/`, not importable from app code).
- `docs/architecture/ML_INTEGRATION.md`: how to add a model, required files, schema versioning, validation checklist, flag switch, how the frontend flips from mock to real.
- Docs: risk categories as a scientific interpretation tied to *calibrated* probabilities (fixed only after validation, never thresholds in code); training-data and validation requirements (spatial-block CV + temporal hold-out; baselines logistic regression and rainfall-only; PR-AUC, recall at fixed false-alarm rate, Brier, calibration; imbalance; inventory-bias caveat).

## Out of scope
Training, fine-tuning, inference, weights, rule-based or hardcoded substitutes, fabricated scores/probabilities/classes. Mock prediction data is **frontend only** (Phase 9).

## Future ML gate (separate stage, not in this roadmap)
Real dated inventory, real Phase 4-6 feature layers, approved validation protocol, approved model family and compute budget.

## Prerequisites
Phases 4-6 schemas (manifest, feature schema, indicators).

## Acceptance
`PREDICTION_BACKEND=none` returns `MODEL_NOT_TRAINED` everywhere; schema validation tests; swap-path test passes with the TEST_DOUBLE; no score-like fields in app code; ADR-0008 (ML slot) followed and updated only if the design changes; ADR-0002 untouched.

## Implementation status
**COMPLETED (2026-11-15), scope = architecture, contracts and an empty ML slot.** All acceptance items met with evidence below; no model, no score. Caveat: Phase 6 now exists (2026-11-15, synthetic only) but does not fill the per-point dynamic features, so the trigger head stays design-only; the slot itself is unaffected.

| Item | Evidence |
|---|---|
| Two heads, analysis units, targets, label caveats, risk-category interpretation, training-data and validation protocol | [PREDICTION_DESIGN](../scientific/PREDICTION_DESIGN.md) (design, *proposed* parameters) |
| Schemas `RiskModelInput` (wraps `ModelInputSpec`), `RiskModelOutput`, `ModelRegistryEntry`, `PredictionResponse` | `backend/app/schemas/prediction.py` |
| `Predictor`, `NullPredictor`, `ModelRegistry`, `PredictionService`, `PREDICTION_BACKEND` (default `none`), `MODELS_DIR` | `backend/app/services/prediction/`, `core/config.py` |
| Endpoints `/api/v1/prediction/status|models|susceptibility|trigger` -> `MODEL_NOT_TRAINED` under `none` | `backend/app/api/v1/prediction.py` |
| Artifact folder, README, template (no weights) | `models/` |
| Swap-path contract test with test-only `TestDouble` | `backend/tests/prediction/` |
| How to add a model, checklist, frontend flip | [ML_INTEGRATION](../architecture/ML_INTEGRATION.md) |

Tests (2026-11-15, Earthdata unset, throwaway database `precursor_t_p78`): `tests/prediction` **29 passed** (Phase 7 + 8 together); whole backend suite **630 passed, 4 skipped, 0 errors** (baseline 601 before Phases 7-8); `alembic check`: no drift (no migration, no DB table). An earlier run without a throwaway database showed 135 DB-guard errors, resolved by creating the database. ADR-0008 followed unchanged; ADR-0002 untouched.

Open (by design, not defects): the registry has never loaded a real model (none exists); `ModelRegistry.attach` wiring at app start belongs to the separately authorized ML stage. Fixed after review: the default service rescans `models/` on each request (a model folder added while the app runs is picked up; attached predictors are kept).

## Constraints
[ADR-0002](../adr/ADR-0002-ml-deferral.md), [ADR-0008](../adr/ADR-0008-ml-slot-and-labelled-mock-frontend.md), [scientific-integrity.md](../../.claude/rules/scientific-integrity.md).

## Known limitations
Landslide catalogs are incomplete and biased toward reported places; GLC last event is dated 2017-09-28 (corrected 2026-11-15, [M1 census](../../ml/reports/M1_census_and_download_list.md)).

## Dependencies
Previous: Phases 4-6. Following: Phase 8 (explainer in the same registry), Phase 9 (UI contract).
