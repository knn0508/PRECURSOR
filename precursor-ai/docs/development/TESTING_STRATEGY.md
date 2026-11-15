# Testing strategy

| Layer | Tool | Where | Notes |
|---|---|---|---|
| Backend unit/API | pytest + FastAPI TestClient | `backend/tests/` | DB tests need PostGIS; skipped (not passed) if unreachable |
| Phase 2 pipeline | pytest with fakes | `backend/tests/data_acquisition/` | NASA mocked at `cmr.py`; synthetic files for validation |
| Phase 4 environmental | pytest, synthetic rasters/files | `backend/tests/environmental/` | numerical oracles, pipeline/API integration (`test_addendum_pipeline.py`: manifest, grids, NOT_AVAILABLE, skip/force); **synthetic only** |
| Phase 3 InSAR | pytest, synthetic HDF5 | `backend/tests/insar/` | numerical oracles, DB/API integration; **synthetic data only: never evidence of real processing** |
| Real-data InSAR | pytest manual | `backend/tests/manual/test_real_insar.py` | skipped unless `REAL_INSAR_FILE` is set; prints a `REAL_DATA_VALIDATION` verdict |
| Live NASA | pytest manual | `backend/tests/manual/test_live_earthdata.py` | skipped unless `RUN_LIVE_EARTHDATA=1` + credentials; user-run |
| Frontend | vitest | `frontend/tests/` | api-client, data helpers, cinematic math |
| Types/lint/build | tsc, eslint, next build | `frontend/` | |
| Validation and robustness | pytest | `backend/tests/validation/`, `backend/tests/test_phase10_security_ops.py` | geometry vs geodesic references, corrupt files, concurrency, DB load, weights/secrets/non-root/CORS checks (Phase 10) |
| Coverage | pytest-cov | `pytest --cov=app` | 94.3 % line coverage on 2026-11-15 (a measure of executed lines, not of scientific correctness) |
| Browser e2e | none | - | Playwright not installed; only the Phase 9 headless-Chrome checks exist |
| CI | GitHub Actions | `.github/workflows/ci.yml` | written in Phase 10, never run (no remote) |

## Rules
- **Tests truncate tables:** always use a throwaway DB via `TEST_DATABASE_URL`, never the dev database. `backend/tests/conftest.py` fails with "refusing to run DB tests" for any database whose name does not start with `precursor_t` (override only with `ALLOW_TESTS_ON_ANY_DATABASE=1`).
- **Set the URL safely.** Do not write `export DATABASE_URL=X TEST_DATABASE_URL="$DATABASE_URL"` on one line (the second expansion happens before the first assignment and can point tests at the dev database; this caused the 2026-11-14 incident, see [PROJECT_MEMORY](../project/PROJECT_MEMORY.md)). Build the URL in its own variable, export from it, and print the database name before running pytest.
- Run backend tests with `EARTHDATA_USERNAME`/`EARTHDATA_PASSWORD` unset; otherwise 3 CLI tests fail (known fragility).
- Never call live NASA services from automated tests. Scientific functions need deterministic unit tests with known inputs.
- Record real counts and dates in PROJECT_STATUS.

Latest results: [PROJECT_STATUS](../project/PROJECT_STATUS.md).
