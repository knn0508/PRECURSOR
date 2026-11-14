# Phase 2: Satellite Data Acquisition

Status: **PARTIALLY_COMPLETED**: implemented and mock-tested; live acquisition NOT_VERIFIED. Canonical implementation guide: [phase-2-data-acquisition.md](../phase-2-data-acquisition.md) (includes the verification matrix). Roadmap: [ROADMAP](../project/ROADMAP.md).

## Objective and scope
Authenticate with Earthdata, find, download, validate and catalogue NISAR (GUNW, GCOV, GSLC, optional GOFF/SME2), NASADEM, GPM IMERG, optional SMAP and the Global Landslide Catalog for a configurable AOI, with provenance. **Out of scope:** InSAR/SAR processing, terrain derivatives, CV, ML, risk.

## Prerequisites
Phase 1 stack. For live work: Earthdata credentials (present in `.env`), an AOI, and user approval of specific downloads.

## Tasks and evidence
| Task | Status | Evidence |
|---|---|---|
| Provider abstraction + 5 providers + ASF fallback | COMPLETED (mocks) | `services/data_acquisition/providers/`, tests |
| Earthdata auth service | COMPLETED (mocks); live NOT_VERIFIED | `authentication.py` |
| AOI handling, size limit | COMPLETED | `aoi.py` |
| Download manager (resume/retry/atomic/checksum) | COMPLETED (mocks) | `download_manager.py` |
| File validation | COMPLETED (synthetic files) | `validation_service.py` |
| Migration `0002` + models | COMPLETED | `alembic check` clean |
| API `/data/*` (13 endpoints), CLI | COMPLETED (mocks) | `tests/data_acquisition/test_api_data.py`, `test_cli.py` |
| Dashboard `/dashboard/data/*` | COMPLETED | rendered against live backend |
| Six docs | COMPLETED | `docs/*.md` |
| Live login + real downloads + real-file validation | **NOT_STARTED** | needs user approval |

## Acceptance (from brief) vs evidence
Search/registration/dedup/validation/API/CLI/UI delivered and mock-tested. Not met: any real authenticated download; real NISAR HDF5 structure; real landslide CSV import; load behaviour of the executor.

## Tests and validation
2026-11-14: 157 passed, 3 skipped (manual live tests), `alembic check` clean. Live: 11 collections discovered; dry-run NISAR GUNW search returned 3 real granules (`metadata_only`); DB unchanged.

## Known limitations
See [PROJECT_STATUS](../project/PROJECT_STATUS.md) open issues 1-10 and the guide's Known limitations. Landslide catalog is a 2016 export; IMERG is not real-time; default maturity filter is VALIDATED only.

## Dependencies
Feeds Phase 3 (NISAR GUNW/GCOV/GSLC), Phase 4 (NASADEM, IMERG, SMAP, catalog).
