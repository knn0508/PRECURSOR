# Phase 10: Testing, Validation & Deployment

Status: **NOT_STARTED** (scope defined 2026-11-14). Roadmap: [ROADMAP](../project/ROADMAP.md). Executable brief: [Prompts.md](../../Prompts.md) (Phase 10).

## Objective
Prove what works, state what does not, and make the platform deployable.

## Scope
1. Test pyramid: unit, integration (API + PostGIS), e2e (Playwright: AOI, search, inventory, processing job, layers, `MODEL_NOT_TRAINED` state and labelled MOCK view; mock banner always present; no mock data in API/DB). Coverage report; every Phase 2-9 bug closed or explicitly accepted.
2. Scientific validation: geospatial calculations vs analytic cases (slope on a known plane, metric distances, CRS round-trips); InSAR vs a reference (known-motion site or published product) with RMSE/bias and tolerance; acquisition on real files (checksum/size/manifest). `REAL_DATA_VALIDATION` per phase: PERFORMED / PARTIAL / NOT_PERFORMED.
3. Early-warning validation: **protocol only, results `NOT_APPLICABLE` (no model exists)**: temporal and spatial hold-out, hit and false-alarm rate, precision, PR-AUC, Brier, calibration, lead time, baselines (rainfall threshold, rainfall-only), confidence intervals, inventory-bias analysis.
4. Robustness: multiple AOIs and UTM zones, antimeridian rejection, missing/corrupt data, interrupted downloads, job recovery, large rasters, concurrency, DB load.
5. Security: secrets handling, path traversal (Phase 2 issue 1), input validation, dependency audit, CORS, auth on write/processing endpoints, rate limiting, container hardening.
6. ML slot checks: `PREDICTION_BACKEND=none` returns `MODEL_NOT_TRAINED` everywhere; `ML_INTEGRATION.md` followed in a dry run with the TEST_DOUBLE; no weights or fabricated outputs ship.
7. Operations: structured logging, error envelope, health/readiness, backups, Alembic up/down, Compose production profile, `.env.example`, CI (lint, types, tests, build, migration check), deployment runbook, user docs.
8. Final validation and limitations report: validated vs not, against what, with what error; biases (inventory, resolution, geometry, vegetation decorrelation); intended use: **research prototype, not an operational warning system**.

## Out of scope
New features beyond fixes; large real-data downloads without user approval.

## Prerequisites
Phases 1-9.

## Acceptance
Real results tables, defects found/fixed, deployment instructions, final report. No phase marked COMPLETED without evidence in its verification table.

## Implementation status
Nothing implemented. CI and Playwright tests: none in repo.

## Constraints
[scientific-integrity.md](../../.claude/rules/scientific-integrity.md), [ADR-0002](../adr/ADR-0002-ml-deferral.md), [ADR-0008](../adr/ADR-0008-ml-slot-and-labelled-mock-frontend.md).

## Known limitations
Validation results do not exist yet: every accuracy, error and performance figure is `NOT_VERIFIED` until this phase records real output. Known from earlier phases: synthetic-only testing (Phases 3-5), unverified InSAR sign convention, no real-data processing so far, no ML model.

## Dependencies
Previous: Phases 1-9.
