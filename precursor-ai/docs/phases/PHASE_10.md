# Phase 10: Testing, Validation & Deployment

Status: **PARTIALLY_COMPLETED** (run 2026-11-15; see the verification table). Roadmap: [ROADMAP](../project/ROADMAP.md). Executable brief: [Prompts.md](../../Prompts.md) (Phase 10).

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
**PARTIALLY_COMPLETED (2026-11-15).** Everything runnable without real data, new downloads or a new dependency decision was run and recorded. Items needing real data, a Playwright install or a product decision are listed as open. No phase is marked COMPLETED on the strength of this phase alone.

### Verification table (all commands run 2026-11-15, Earthdata variables unset)
| Item | Result | Evidence |
|---|---|---|
| Backend suite (throwaway DB `precursor_t_p78`) | **701 passed, 4 skipped, 0 failed** (651 before Phase 10, +50) | `pytest tests`; skipped = 3 manual live Earthdata + 1 manual real InSAR |
| Backend coverage (`pytest-cov`) | **94.3 %** (10,795 of 11,449 statements); lowest: `app/main.py` 45.8 %, `services/data_acquisition` 91.1 %, `app/cli` 92.1 %, `services/environmental` 93.3 % | `--cov=app`; line coverage of synthetic/mock tests, not evidence of scientific correctness |
| Alembic | head 0005; downgrade to base (5 steps) and upgrade to head (5 steps) succeeded; `alembic check`: no new upgrade operations | run on the throwaway DB |
| Frontend | `tsc --noEmit` clean, `npm run lint` clean, vitest **107 passed** (10 files), `npm run build` passes | |
| Dependency audit | `npm audit`: 0 vulnerabilities (prod and full); `pip-audit -r requirements.txt --no-deps`: no known vulnerabilities (transitive packages not audited) | |
| Geometry validation vs independent geodesic reference | PASS within stated tolerances (distance <= 0.051 %, area <= 0.102 %, round-trip <= 1.4e-14 deg) for 7 AOIs on 6 continents/zones, polar case, antimeridian rejection | `tests/validation/test_phase10_validation.py`, [VALIDATION_REPORT](../scientific/VALIDATION_REPORT.md) |
| Robustness | corrupt/empty raster and HDF5 fail cleanly; 64 concurrent requests OK; 3,000-event bbox query 0.57 s | same file; plus existing resume/checksum/stale-job tests |
| Security | secrets/`.env.example`, non-root minimal containers, CORS allow-list, no stack traces: tested; Phase 2 issues 1, 2, 7, 8 fixed with regression tests | `tests/test_phase10_security_ops.py`, `tests/data_acquisition/test_phase10_fixes.py` |
| ML slot | default `none`; all prediction routes `MODEL_NOT_TRAINED`/`MODEL_NOT_AVAILABLE`; no weights or `metadata.json` ship; swap path proven with the test double (Phase 7 tests) | `tests/test_phase10_security_ops.py` |
| Operations files | `docker-compose.prod.yml` passes `docker compose config`; `scripts/backup.sh` core (pg_dump custom format + restore into a fresh DB) verified; CI workflow, runbook and user guide written | not deployed, CI not run remotely |
| Early-warning validation | **NOT_APPLICABLE** (no model); protocol written | [EARLY_WARNING_VALIDATION_PROTOCOL](../scientific/EARLY_WARNING_VALIDATION_PROTOCOL.md) |
| Playwright e2e | **NOT_PERFORMED**: Playwright and its browsers are not installed (new dependency plus browser download, not approved); the live headless-Chrome runs of Phase 9 are the only browser evidence | |
| InSAR vs reference, real-file acquisition validation | **NOT_PERFORMED**: no real file | VALIDATION_REPORT |
| Auth, rate limiting | **NOT IMPLEMENTED**: new features, product decision needed; documented as the main deployment risk | DEPLOYMENT_RUNBOOK |

### Defects found and fixed in Phase 10
1. (Phase 2 #1) `POST /landslide-events/import` read any server path: now confined to the data root (traversal, parent, system and absolute paths refused; CLI unaffected).
2. (Phase 2 #2) `POST /downloads` queued jobs that could never download: now fails fast with HTTP 412 `credentials_missing` before anything is queued.
3. (Phase 2 #7) `retry_job` kept the old attempt count: now resets attempts, progress and bytes (an older test had asserted the buggy value 2; updated to 1).
4. (Phase 2 #8) Tests failed when real Earthdata credentials were exported: an autouse fixture now clears them (verified by running with fake credentials exported).
Found, not fixed: `EnvError` messages for unreadable rasters include the server-side file path (minor information disclosure through the API).

### Disposition of earlier open issues
| Issues | Disposition |
|---|---|
| Phase 2: 1, 2, 7, 8 | **closed** (above) |
| Phase 2: 5 (file-name prefix with `dest_dir`), 6 (ASF provider reports `name=NISAR`, no explicit timeout) | **accepted**: cosmetic or would change the provider enum stored in the database; revisit with real NISAR use |
| Phase 2: 3 (50,000-file walk cap), 4 (`UNAVAILABLE` never set), 9, 10, 11 (no git commits) | accepted/open; 9 and 10 need a real catalog and real files |
| Phase 3: 13-18, 21; Phase 4: 22-34; Phase 5: 35-40; Phase 6: 41-44; Phase 8 caller-supplied geometry; Phase 9: 45-48 | **blocked on real data or on the ML stage**; unchanged and listed in PROJECT_STATUS |
| No authentication or rate limiting | **open, decision needed** |
## Constraints
[scientific-integrity.md](../../.claude/rules/scientific-integrity.md), [ADR-0002](../adr/ADR-0002-ml-deferral.md), [ADR-0008](../adr/ADR-0008-ml-slot-and-labelled-mock-frontend.md).

## Known limitations
Recorded in [VALIDATION_REPORT](../scientific/VALIDATION_REPORT.md): geometry validated analytically; every real-data, InSAR-accuracy and early-warning figure remains `NOT_PERFORMED`/`NOT_APPLICABLE`. Known from earlier phases: synthetic-only testing (Phases 3-5), unverified InSAR sign convention, no real-data processing so far, no ML model.

## Dependencies
Previous: Phases 1-9.
