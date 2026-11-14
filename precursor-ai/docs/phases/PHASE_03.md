# Phase 3: SAR Image Processing & InSAR Analysis

Status: **PARTIALLY_COMPLETED**: implemented and tested with synthetic fixtures. Docker-verified with a synthetic file (stack healthy, live API run, headless-browser page check). **`REAL_DATA_VALIDATION: NOT_PERFORMED`**: no real NISAR or Sentinel-1 file has been downloaded or processed. Roadmap: [ROADMAP](../project/ROADMAP.md). Method: [INSAR_METHODOLOGY](../scientific/INSAR_METHODOLOGY.md). Decision: [ADR-0004](../adr/ADR-0004-insar-placement-and-strategy.md).

## Objective and scope
Deterministic inspection and processing of SAR products already downloaded in Phase 2: product-aware adapters, LOS displacement from unwrapped phase, coherence handling, preliminary mean velocity, quality reports, COG outputs, run tracking, API and a minimal UI. **Out of scope:** acquisition/downloads, time-series/forecasting (Phase 6), terrain/environmental integration (Phase 4), CV (Phase 5), any ML, risk maps (Phase 7).

## Prerequisites
Phase 2 database and storage. For real results: a downloaded, user-approved NISAR file (not yet available).

## Tasks and evidence
| Task | Status | Evidence |
|---|---|---|
| Phase 2 integration audit | COMPLETED | inputs = `data_acquisitions` rows with a file under `data/raw`; no Phase 2 code changed except `main.py` lifespan, `Dockerfile`, `requirements.txt`, `config.py` additions |
| Adapters: GUNW, GSLC, GCOV, Sentinel-1 | COMPLETED (synthetic) | `services/insar/adapters/`, `tests/insar/test_inspection.py` |
| Inspection service (HDF5/SAFE detection, metadata, missing/warnings) | COMPLETED (synthetic) | `inspection.py` |
| Phase -> displacement, coherence, velocity | COMPLETED, numerically tested | `tests/insar/test_scientific.py`, `test_processing.py` |
| Wrapped interferogram + coherence estimation | IMPLEMENTED, not wired into runs | unit tests only |
| Phase unwrapping / SLC interferometry / TOPS | **NOT_IMPLEMENTED by design** | needs external tools (not installed) |
| External tool gate (SNAP/ISCE/SNAPHU) | COMPLETED (stand-in executable tests) | `external.py` |
| Run orchestration, duplicate control, cancel, recovery | COMPLETED | `runs.py`, `tests/insar/test_runs_api.py` |
| Migration `0003`, models | COMPLETED | upgrade/downgrade/upgrade verified; `alembic check` clean |
| API `/api/v1/insar/*` | COMPLETED (synthetic) | `app/api/v1/insar.py` |
| COG/GeoTIFF, preview PNG, metadata, quality JSON | COMPLETED (synthetic) | `outputs.py`, `processing.py` |
| Frontend `/dashboard/insar` | COMPLETED (minimal) | `components/insar/`, `tests/insar-helpers.test.ts` |
| Manual real-data test | PROVIDED, not run | `tests/manual/test_real_insar.py` |
| Real-data processing and validation | **NOT_STARTED** | needs a real file |

## Acceptance (from the brief) vs evidence
Architecture/integration: met. Scientific functionality: met on synthetic data; GSLC and GCOV are inspection-only; Sentinel-1 is an adapter with a blocked execution path. Application integration: met for API (TestClient), database and frontend unit tests/build; Docker services healthy and the page rendered against the live backend, with a synthetic file only. Transparency: synthetic data labelled everywhere; no ML; real-data validation stated as NOT_PERFORMED. **Not met:** end-to-end real-data validation, sign-convention verification, Sentinel-1 processing.

## Tests and validation
Counts and dates: [PROJECT_STATUS](../project/PROJECT_STATUS.md). Passing synthetic tests is not evidence that real satellite processing is correct.

## Known limitations
HDF5 paths discovered by name, unverified against a real granule; sign convention unverified; no reference point, atmospheric or ionospheric correction; velocity is single-interferogram mean; GUNW multi-polarization needs an explicit choice; no unwrapping; single-worker in-process queue lost on restart (stale runs marked FAILED); `ai_engine/insar` stays a README.

## Dependencies
Needs Phase 2 downloads. Feeds Phase 4 (aligned layers), Phase 5 (features), Phase 6 (time series). Deformation products are not risk products.
