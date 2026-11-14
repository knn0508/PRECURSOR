# Environment setup

Full steps: [README](../../README.md). Variables: `.env.example` (names only; `.env` is gitignored). Earthdata specifics: [../earthdata-authentication.md](../earthdata-authentication.md).

- Prerequisites: Docker Desktop; or Python 3.11+ (Docker image uses 3.12), Node 20+, PostGIS.
- Stack: `docker compose up -d --build` -> frontend :3000, API :8000/docs, Postgres host port **55432**.
- Backend venv: `backend/.venv` (`pip install -r requirements-dev.txt`). Windows python: `.venv/Scripts/python`.
- Required for Phase 2 downloads: `EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD` (or `~/.netrc`). Never print or commit them. Search works without.
- Key Phase 2 settings: `DATA_ROOT`, `ALLOWED_MATURITIES` (default VALIDATED), `MAX_FILE_SIZE_BYTES` (3 GiB), `MAX_GRANULES_PER_REQUEST` (10), `MAX_AOI_BBOX_DEGREES` (5), `ENABLE_*`.
- Machine quirk: PostgreSQL's `PROJ_LIB` breaks rasterio; handled by `app/core/geo_env.py`.
- Test DB: create a separate PostGIS database whose name starts with `precursor_t` and set `TEST_DATABASE_URL`; the test conftest refuses any other name unless `ALLOW_TESTS_ON_ANY_DATABASE=1` is set (do not set it casually: tests truncate tables). Build the URL in its own variable and export from it, never `export DATABASE_URL=X TEST_DATABASE_URL="$DATABASE_URL"` on one line. Details: [TESTING_STRATEGY](TESTING_STRATEGY.md).
