# Phase 7: Predictive Risk Assessment Engine (architecture and ML slot, no ML)

Status: **NOT_STARTED** (scope defined 2026-11-14; no code). Roadmap: [ROADMAP](../project/ROADMAP.md). Executable brief: [Prompts.md](../../Prompts.md) (Phase 7).

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
Nothing implemented. Tests: none.

## Constraints
[ADR-0002](../adr/ADR-0002-ml-deferral.md), [ADR-0008](../adr/ADR-0008-ml-slot-and-labelled-mock-frontend.md), [scientific-integrity.md](../../.claude/rules/scientific-integrity.md).

## Known limitations
Landslide catalogs are incomplete and biased toward reported places; GLC ends 2016-03-07.

## Dependencies
Previous: Phases 4-6. Following: Phase 8 (explainer in the same registry), Phase 9 (UI contract).
