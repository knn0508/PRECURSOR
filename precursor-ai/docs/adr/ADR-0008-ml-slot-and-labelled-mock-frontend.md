# ADR-0008: Reserve an ML slot and allow labelled frontend mock predictions (no ML)

- Status: ACCEPTED
- Date: 2026-11-14 (user decision)
- Clarifies, does not reverse, [ADR-0002](ADR-0002-ml-deferral.md)

## Context
The product goal is landslide early prediction, but ML stays deferred (ADR-0002). The user will add their own finished model later and wants the project to have a defined place for it now, and a frontend that can be designed and tested before a model exists.

## Decision
1. **No ML/DL is trained, fine-tuned or run in the 10-phase roadmap.** ADR-0002 stands: no rule-based or hardcoded stand-ins, no fabricated scores in backend, DB or API.
2. **ML slot (Phase 7).** `backend/app/services/prediction/`: `Predictor` protocol, `NullPredictor`, `ModelRegistry`; artifacts in `models/<model_id>/<version>/` (model card, metadata, feature schema, provenance; empty except README and template); config `PREDICTION_BACKEND = none | registered_model`, default `none`; API `/api/v1/prediction/*` returns `MODEL_NOT_TRAINED` under `none`. Enabling a model changes responses only, not routes or schemas. A `TEST_DOUBLE` predictor exists only under `tests/` to prove the swap path.
3. **One feature contract.** The Phase 5 `ModelInputSpec` (`features_cv/schema.py`, with `validate_against`) IS the model-input contract. The Phase 7 registry imports and calls it at model-load time; it must not define a second input schema. Phase 7 adds only the output side (`RiskModelOutput`, registry entry, model card).
4. **Labelled mock in the frontend only (Phase 9).** Mock prediction views live in a separate fixture module, behind a flag that is **OFF by default** (default UI keeps "N/A until a real, validated source exists"). When ON: persistent `MOCK DATA: NOT A PREDICTION` banner and badge, seeded generator unrelated to real inputs, neutral palette (no risk colours), no export. Never in backend, DB or API. A real-response path is built and tested with `TEST_FIXTURE` data and activates when the API stops returning `MODEL_NOT_TRAINED`.
5. **Real ML** remains a separate, explicitly authorized stage after Phase 10. Its gate: a real dated inventory, real Phase 4-6 features, an approved validation protocol, an approved model family and compute budget.

## Alternatives considered
- Mock data in backend (rejected: could leak into API/DB as if real).
- No frontend placeholder until a model exists (rejected: blocks UI design and e2e tests).
- A second input schema in Phase 7 (rejected: duplicates `ModelInputSpec`).

## Consequences
Frontend rule "risk cards show N/A" holds by default; mock is an explicit, labelled demo mode. Phases 7-10 docs and prompts follow this ADR. Phase 7 must not rewrite ADR-0002.

## Related
See also [ADR-0009](ADR-0009-ml-development-track.md) (real-ML development track, isolated under `ml/`).
[ROADMAP](../project/ROADMAP.md), [scientific-integrity.md](../../.claude/rules/scientific-integrity.md), [Prompts.md](../../Prompts.md), [PHASE_07](../phases/PHASE_07.md), [PHASE_09](../phases/PHASE_09.md)
