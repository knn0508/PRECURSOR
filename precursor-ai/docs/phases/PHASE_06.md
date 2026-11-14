# Phase 6: Time Series Analysis & Deformation Forecasting

Status: **NOT_STARTED** (scope defined 2026-11-14; no code). Roadmap: [ROADMAP](../project/ROADMAP.md). Executable brief: [Prompts.md](../../Prompts.md) (Phase 6).

## Objective
Turn dynamic observations (InSAR deformation, coherence, rainfall, SMAP soil moisture) into analysis-ready time series and **deterministic** trigger indicators for landslide early prediction. Statistical description only.

## Scope
- Chronological series per AOI / zone / pixel; every point keeps source, sensor, geometry (track, look direction), quality and synthetic flag.
- Gap and irregular-interval analysis; no silent interpolation (optional gap filling is explicit, labelled, off by default).
- Documented deterministic indicators: linear trend with confidence interval, Theil-Sen, Mann-Kendall, velocity change between windows, acceleration only with at least N compatible acquisitions (N stated), rainfall antecedent indices (1/3/7/14/30-day, API), descriptive storm statistics, rainfall-deformation lag as a **descriptive** statistic (correlation is not causation).
- Per-point dynamic features: fills the columns Phase 5 reserved (`NOT_AVAILABLE`, deferred to Phase 6), with lead-time anchors t-1/3/7/14/30 days.
- Mixed-geometry guard: ascending vs descending and different sensors are never merged without a documented decomposition.
- Forecasting **interface only**: `Forecaster` protocol, schemas, `NotImplementedForecaster` returning `NOT_IMPLEMENTED`. No persistence or linear extrapolation presented as a forecast.
- Per-series limitations report: n, span, median interval, gaps, aliasing risk.

## Out of scope
ML forecasting, fabricated future deformation, rainfall thresholds used as alerts, risk labels, the full Phase 9 dashboard (a minimal Recharts test page is allowed).

## Prerequisites
Phase 3 products with dates, Phase 4 dynamic layers, Phase 5 dataset schema. Real multi-date data does not exist yet: build and test on **labelled synthetic** series; status stays at most PARTIALLY_COMPLETED.

## Expected deliverables
Time-series store and service, indicator functions with analytic tests, forecaster interface, limitations docs (`docs/scientific/`), updated status docs.

## Acceptance
Known-trend recovery within a stated tolerance, gap/irregular sampling handled, short series refused, mixed-geometry refused, no score-like fields, `REAL_DATA_VALIDATION` recorded honestly.

## Implementation status
Nothing implemented. Tests: none.

## Constraints
ML policy: [ADR-0002](../adr/ADR-0002-ml-deferral.md). Scientific rules: [scientific-integrity.md](../../.claude/rules/scientific-integrity.md). Geospatial rules: [geospatial.md](../../.claude/rules/geospatial.md).

## Known limitations
IMERG is not real-time and ~10 km; SMAP is ~9-36 km; InSAR sign convention unverified (Phase 3 issue 14); LOS is not vertical.

## Dependencies
Previous: Phases 3-5. Following: Phase 7 (trigger-head inputs), Phase 8 (temporal-gap uncertainty), Phase 9 (charts).
