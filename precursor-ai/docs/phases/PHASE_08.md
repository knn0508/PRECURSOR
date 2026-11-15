# Phase 8: Uncertainty Quantification & Explainability (interfaces and quality metadata)

Status: **COMPLETED** (interfaces and quality metadata, 2026-11-15; see Implementation status). Roadmap: [ROADMAP](../project/ROADMAP.md). Executable brief: [Prompts.md](../../Prompts.md) (Phase 8).

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
**COMPLETED (2026-11-15), scope = interfaces and quality metadata.** Ledger, masks, one analytic propagation, reliability rules and the explainer slot are implemented and tested on hand-made/synthetic inputs; no model, so no explanation or predictive confidence exists (by design).

| Item | Evidence |
|---|---|
| `UncertaintyReport` ledger from Phase 3-5 metadata | `services/uncertainty/ledger.py`, `GET /uncertainty/areas/{id}/report` |
| Coverage/limitation masks (coherence, vegetation, layover/shadow, LOS sensitivity) | `services/uncertainty/masks.py`; rules in [UNCERTAINTY_AND_RELIABILITY](../scientific/UNCERTAINTY_AND_RELIABILITY.md) |
| `UncertaintySource`/`Propagator`; coherence -> phase std -> LOS std (Cramer-Rao lower bound) | `services/uncertainty/propagation.py`; hand-computed test values |
| `Explainer`, `Explanation`, `FeatureContribution`, `explainer.json`, `POST /prediction/explain` -> `MODEL_NOT_AVAILABLE` | `services/prediction/{explainer,registry,service}.py` |
| Reliability (suppression) conditions | `services/uncertainty/reliability.py` + doc section 4 |

Tests (2026-11-15, Earthdata unset, throwaway database `precursor_t_p78`): `tests/prediction` **29 passed**; whole backend suite **630 passed, 4 skipped, 0 errors**; `alembic check` clean; frontend `tsc --noEmit` clean. Bugs found by tests and fixed: LOS sensitivity on flat cells returned a number (now NaN, flagged); the skipped-layer ledger message printed the whole dict (now layer and reason).

Limitations / open (not fixable without real data or later phases): masks take look azimuth, incidence and thresholds from the caller because Phase 3 records only `orbit_direction` and `wavelength_m` (no incidence angle, look azimuth or effective looks); thresholds need real-data justification; the propagation formula matches two secondary sources (see the science doc) but the original papers were not read; suppression rules are not wired into prediction responses (no model); no Phase 6 metadata exists; no SHAP/LIME, calibration or conformal work (out of scope).

## Constraints
[ADR-0002](../adr/ADR-0002-ml-deferral.md), [ADR-0008](../adr/ADR-0008-ml-slot-and-labelled-mock-frontend.md), [scientific-integrity.md](../../.claude/rules/scientific-integrity.md).

## Known limitations
Explanations are never causal; they require a real model, which does not exist.

## Dependencies
Previous: Phases 3-7. Following: Phase 9 panels, Phase 10 checks.
