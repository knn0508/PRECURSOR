# ADR-0009: ML development track authorized, isolated from the 10 phases

- Status: ACCEPTED
- Date: 2026-11-15 (user decision)
- Supplements [ADR-0002](ADR-0002-ml-deferral.md) and [ADR-0008](ADR-0008-ml-slot-and-labelled-mock-frontend.md); neither decision is changed.

## Context
ADR-0002 deferred real ML to "a separate phase, authorized explicitly". ADR-0008 reserved the ML slot and named the gate for real ML. The user now authorizes that separate effort as a parallel track (M0-M9, see the last section of [Prompts.md](../../Prompts.md)) so models can be developed while Phases 6-10 proceed without ML.

## Decision
1. **Isolation.** ML work lives only under `ml/` (code, configs, notebooks, reports, tests) and `data/ml/` (data). Status docs live in `docs/ml/`. Existing backend code may be imported read-only; it is not modified without the user's approval and a regression test.
2. **No wiring.** Nothing from the track is wired into the backend, frontend, API or database. `PREDICTION_BACKEND` stays `none`.
3. **Handoff.** A trained model enters the product only through the ADR-0008 slot (`models/<model_id>/<version>/`, `ModelInputSpec`), and only when the user decides (stage M9).
4. **Phases stay ML-free.** The 10 roadmap phases and their statuses are unchanged; Phases 6-10 follow their prompts without ML.
5. **Real-data-only performance claims.** Synthetic data is allowed only for labelled pipeline smoke tests; a model trained or scored on synthetic data is never reported as a result. Held-out, spatially and temporally split evaluation only.
6. **Stop points.** M1, M5, M7, M9 wait for the user's explicit answer; no stage starts on its own. M0 ends with approval of the dependency list.

## Alternatives considered
- Wait until after Phase 10 (rejected by the user: slows model development).
- Put ML inside `backend/app/services/` (rejected: couples experiments to the production image and API).

## Consequences
- Rule files get one scoped exception paragraph; every other ML prohibition stays.
- A separate ML environment (own requirements, not the backend image) is needed; dependencies need the user's approval ([ML_ENVIRONMENT](../ml/ML_ENVIRONMENT.md)).
- A scope guard (`ml/scripts/check_scope.py`) detects accidental edits outside the track.

## Related
[ml.md rules](../../.claude/rules/ml.md), [ML_STATUS](../ml/ML_STATUS.md), [scientific-integrity.md](../../.claude/rules/scientific-integrity.md), [Prompts.md](../../Prompts.md)
