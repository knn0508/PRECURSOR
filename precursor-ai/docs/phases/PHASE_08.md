# Phase 8: Uncertainty Quantification & Explainability (interfaces and quality metadata)

Status: **NOT_STARTED** (scope defined 2026-11-14; no code). Roadmap: [ROADMAP](../project/ROADMAP.md). Executable brief: [Prompts.md](../../Prompts.md) (Phase 8).

## Objective
Make future outputs transparent: carry data-quality and uncertainty metadata end to end and define explainability interfaces. No model exists, so **no explanation or confidence is generated**.

## Scope
- Uncertainty ledger: propagate quality metadata from Phases 2-6 (coverage, resolution mismatch, temporal gaps, InSAR coherence/decorrelation, sign-convention-unverified, synthetic flags) into a per-output `UncertaintyReport`.
- Coverage and limitation masks (low coherence, vegetation decorrelation, layover/shadow, steep slopes unfavourable to LOS): deterministic data-quality masks with documented rules. They are **not** risk.
- `UncertaintySource` / `Propagator` interfaces; analytic propagation only where a cited formula exists (e.g. phase to LOS displacement).
- Explainability: `Explainer` protocol, `FeatureContribution` and `Explanation` schemas (global vs local, background-dataset reference, model id link), registered per model in the Phase 7 registry (`explainer.json`); returns `MODEL_NOT_AVAILABLE` under `PREDICTION_BACKEND=none`.
- Reliability-conditions doc: when an output must be suppressed (outside valid region/time, insufficient coverage).

## Out of scope
SHAP/LIME runs, calibration or conformal analysis, fabricated explanations or confidence numbers.

## Prerequisites
Phases 2-7 metadata and the Phase 7 registry.

## Acceptance
Schema validation, mask determinism, propagation formula against hand-computed values, `MODEL_NOT_AVAILABLE` behaviour.

## Implementation status
Nothing implemented. Tests: none.

## Constraints
[ADR-0002](../adr/ADR-0002-ml-deferral.md), [ADR-0008](../adr/ADR-0008-ml-slot-and-labelled-mock-frontend.md), [scientific-integrity.md](../../.claude/rules/scientific-integrity.md).

## Known limitations
Explanations are never causal; they require a real model, which does not exist.

## Dependencies
Previous: Phases 3-7. Following: Phase 9 panels, Phase 10 checks.
