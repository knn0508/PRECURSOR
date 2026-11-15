# Project memory

Durable knowledge only. No task progress (see [PROJECT_STATUS](PROJECT_STATUS.md), [TASK_LOG](TASK_LOG.md)). Distinct from Claude Code's private auto-memory.

## Vision
PRECURSOR AI: scientific platform that analyzes SAR observations (Sentinel-1, NASA NISAR), monitors ground deformation, integrates environmental/geospatial data, and eventually estimates landslide risk with uncertainty. Built for NASA Space Apps *Dancing with the SARs*. Roadmap: [ROADMAP](ROADMAP.md).

## User decisions
- 10-phase roadmap is fixed; one phase per task; never auto-start the next ([ROADMAP](ROADMAP.md)).
- **ML/DL are placeholders** until a separately authorized phase after the roadmap is reviewed. No training, inference, fabricated scores, or rule-based stand-ins. Real deterministic science is allowed ([ADR-0002](../adr/ADR-0002-ml-deferral.md)).
- **Nothing is downloaded and no Earthdata login attempted without the user approving specific files** (name, source, size). Agreed during Phase 2.
- Earthdata credentials live only in gitignored `.env`; never printed, logged, committed or returned by the API.
- Use subagents for large phase work (Phase 2 was built that way).

## Confirmed architecture decisions
See [ADR-0001](../adr/ADR-0001-initial-architecture.md) (stack/layering) and [ADR-0003](../adr/ADR-0003-nasa-provider-abstraction.md) (providers, `cmr.py` seam, in-process job executor). Detail: [architecture docs](../architecture/SYSTEM_OVERVIEW.md).

## Scientific constraints
- A catalog hit is not a download; a download is not scientific validation. `VALIDATED` = file integrity only.
- Never claim a dataset exists for an AOI until the catalog confirms it. Never silently mix maturities (VALIDATED default; PROVISIONAL/BETA opt-in). No validated NISAR soil-moisture (SME2) product existed at last check.
- IMERG Final Run: ~0.1 degree, ~3.5-month latency, not real-time.
- Global Landslide Catalog: one-time export, last event dated 2017-09-28 (corrected 2026-11-15, see ml/reports/M1_census_and_download_list.md); incomplete; absence of an event proves nothing.
- GUNW gives LOS displacement only. Deformation is not proof of imminent landslide. See [scientific docs](../scientific/SCIENTIFIC_LIMITATIONS.md).

## Implementation discoveries
- `PROJ_LIB` on the dev machine points at PostgreSQL's `proj.db`, breaking rasterio CRS; fixed in `app/core/geo_env.py` (import first).
- Alembic needs `include_object` to ignore PostGIS/tiger tables, else false drift.
- Host Postgres published on **55432** (5432/5433 taken locally).
- MapLibre worker must be served statically (`/vendor/maplibre-gl-worker.js`) under Turbopack.
- CMR spatial search returns supersets; re-check footprints with shapely.
- Real GUNW granules are ~1.2-2.0 GB; default per-file cap 3 GiB.
- NASA access is isolated behind `services/data_acquisition/cmr.py` so tests can mock it.

## Phase 3 decisions and discoveries
- InSAR code lives in `backend/app/services/insar/`, not `ai_engine/` (Docker build context is `./backend`): [ADR-0004](../adr/ADR-0004-insar-placement-and-strategy.md).
- Processing inputs are Phase 2 `data_acquisitions` rows with a file under `data/raw` (or labelled files in `data/samples/insar`). Phase 3 never downloads and never uses credentials; the API accepts no filesystem paths.
- Never write an unwrapper or SLC processor from scratch to force an output; delegate to SNAP/ISCE/SNAPHU when installed.
- Data origin labels (`SYNTHETIC_FIXTURE`, `REAL_SATELLITE`, `LOCAL_UNVERIFIED`) travel with every run and product; `scientifically_validated` stays false and `real_data_validation` reads NOT_PERFORMED until a real file has been processed and checked.
- HDF5 dataset paths are discovered by name because the real layout is unverified; phase sign convention is assumed `d = -(lambda/4pi)*phi` and flagged unverified.
- A deformation raster is a measurement, never a risk map.
- rasterio needs `libexpat1` in the slim Docker image; importing it lazily had hidden this.

## Phase 4 decisions and discoveries
- Environmental code lives in `backend/app/services/environmental/`; design in [ADR-0005](../adr/ADR-0005-environmental-integration-design.md). Inputs are Phase 2 files/rows, `data/external/<provider>/` and DB tables; no downloads. Soil and land cover produce statistics only (no map raster yet).
- A missing input ends a stage NOT_AVAILABLE with a reason; a run is PARTIAL whenever anything is missing/partial/failed. Missing data is never zero; rolling/monthly rainfall sums need complete windows.
- Slope uses metre cell sizes for geographic grids (never degrees as metres); aspect is circular (clockwise from north, flat = no-data); categorical rasters use nearest neighbour only.
- Phase 3 InSAR products are referenced: only REAL_SATELLITE ones feed features; synthetic/unverified stay labelled and excluded. Catalog rows are labelled LOCAL_UNVERIFIED, not real-satellite.
- The IMERG reader refuses square grids without dimension scales (axis order ambiguous). The brief said Recharts was installed; it was not (added in Phase 4).
- Unverified from official sources: IMERG daily layout/units/fill, NASADEM void and datum, USGS time/depth units and rate limit, SoilGrids CRS/nodata/URLs, WorldCover nodata/tile naming.

## Phase 4 completion addendum: decisions
- Stack manifest, `temporal_kind`, reference grid and alignment: design in [ADR-0006](../adr/ADR-0006-stack-manifest-and-reference-grid.md); native files are always kept, aligned copies are separate. Pipeline is 16 stages.
- Lithology, NDVI and river/fault/road layers are user-provided files in `data/external/<subdir>/`; nothing is downloaded. Vectors are GeoJSON only (fiona/pyogrio/geopandas are not installed; Shapefile/GeoPackage need an approved dependency). Lithology names come only from the user's sidecar legend, never invented.
- SMAP and the new layers are IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA; Phase 4 stays PARTIALLY_COMPLETED until real-data verification ([PROJECT_STATUS](PROJECT_STATUS.md)).
- Later Phase 5 code location chosen by the user: `backend/app/services/features_cv/` (own ADR then).

## Phase 5 decisions and discoveries
- Code in `backend/app/services/features_cv/` ([ADR-0007](../adr/ADR-0007-feature-extraction-and-labelled-dataset.md)); persistence is files plus `manifest.json` (no table, no migration); the API is read-only; runs are CLI/service only.
- scipy, scikit-image and pyarrow were approved and pinned (ADR-0005's scipy rejection no longer holds for Phase 5). opencv-python-headless and torch are NOT approved; the PyTorch Dataset interface is a lazy import that is never run.
- Unlabelled samples are BACKGROUND, never "negatives" (the catalog is incomplete and biased toward reported places). Per-point dynamic features are deferred to Phase 6 and their columns are NOT_AVAILABLE; no AOI-mean proxies.
- Events with unknown/unparseable `location_accuracy` or no date are excluded and listed, never repaired; background buffer = max(2 x accuracy radius, minimum buffer) around every located event. The accuracy vocabulary is NOT_VERIFIED.
- Change features need two dated REAL inputs; with the Phase 4 stack (one layer per type) they are always NOT_AVAILABLE.
- Feature names, columns and manifest keys may not contain score-like words (risk, probab, susceptib, predict, score, hazard, danger, unstable, forecast); a test and the writers enforce it. `ModelInputSpec` is the contract the Phase 7 registry will validate a model against (MAJOR schema version must match).
- Windowed COG writing: write tags BEFORE the COG copy; editing a COG afterwards raises a layout-break error.
- A synthetic world must be larger than the event buffers or no background samples fit (a reported shortfall, not a bug).

## Phase 7-8 decisions and discoveries
- The ML slot is contracts only: `PredictionService` answers `MODEL_NOT_TRAINED` / `MODEL_NOT_AVAILABLE` unless a predictor/explainer is explicitly attached to a registry entry that passed the model-card, provenance, region/time and `ModelInputSpec` checks. Mock/TEST_DOUBLE objects live only in `backend/tests/`.
- Phase 8 quality masks flag NaN (missing is not usable); a flat cell has no aspect, so LOS sensitivity is NaN there. Phase 3 does not record incidence angle, look azimuth or effective looks, which limits automatic propagation.
- A throwaway test DB: `docker exec <postgres container> psql -U precursor -d postgres -c "CREATE DATABASE precursor_t_x"` plus `CREATE EXTENSION postgis`; build the URL in a shell variable without echoing the password.

## Phase 6 decisions and discoveries
- Time series use scipy/numpy ([ADR-0010](../adr/ADR-0010-time-series-with-scipy-no-statsmodels.md)); Mann-Kendall is written out (scipy has none). Indicator minimum N values are working choices and every indicator refuses below its N.
- A series object cannot be built with mixed sensors or LOS geometry, so the guard cannot be bypassed by a caller.
- Phase 3 gives independent pairs, not a displacement time series; only pair mean velocities at mid-time are series-able and they are serially dependent.
- The Phase 5 score-word guard also catches the key `aliasing_risk` (the word risk); named `aliasing` instead.

## Phase 9 decisions and discoveries
- Mock predictions live only in `frontend/lib/mock-predictions.ts` (functions take only a seed and sizes, so no real value can enter) and render only when the API says MODEL_NOT_TRAINED AND `NEXT_PUBLIC_USE_MOCK_PREDICTIONS=true`; a real `OK` response always wins over mock. Component tests use `react-dom/server` with `createElement` in `.ts` files (no testing-library installed).
- Mock views must not use the amber/red/green utility classes, including through shared badges; the PLACEHOLDER source badge is neutral for that reason. A near-neutral grey ramp is used (slate has a blue tint).
- `next dev` allows one server per project directory; to test two flag values run them one after the other. The backend CORS list is only `http://localhost:3000`, so a live check from another dev port needs web security off.

## Phase 10 decisions and discoveries
- A test that asserts a known bug (retry attempts == 2) must be updated together with the fix, with a comment naming the issue.
- `assert not path.glob(...)` is vacuous (a generator is truthy): wrap in `list` or a comprehension.
- Fixtures that must hide real credentials belong in an autouse fixture in `tests/conftest.py` (also clear the `get_settings` cache).
- Throwaway test database recipe is in the runbook and PROJECT_MEMORY earlier section; `docker exec <postgres> printenv POSTGRES_PASSWORD` into a shell variable avoids printing the secret.
- Auth and rate limiting do not exist: the API must not be exposed beyond a trusted network until they do.

## Known limitations
Live downloads, real-file validation, real InSAR processing, GLC date order, NISAR HDF5 layout and the phase sign convention are unverified; in-process job queue is lost on restart. Full list: [PROJECT_STATUS](PROJECT_STATUS.md).

## Do not repeat
- Writing files via bash heredocs when text has apostrophes (use the Write tool).
- Running backend tests against the dev database (tests truncate tables) or with real Earthdata credentials exported (3 CLI tests then fail). **Incident 2026-11-14:** `export DATABASE_URL=X TEST_DATABASE_URL="$DATABASE_URL"` on ONE line expands `$DATABASE_URL` before X is assigned, so `TEST_DATABASE_URL` pointed at the development database `precursor` and tests truncated it (the 11 Phase 2 NASA collections were lost; metadata only, restorable with the anonymous catalog refresh). Always build the URL in its own variable, export from it, and print the database name before running pytest. `backend/tests/conftest.py` now refuses DB tests unless the database name starts with `precursor_t` (override only `ALLOW_TESTS_ON_ANY_DATABASE=1`).
- Claiming completion from file presence; marking features done that only exist as plans.
- Putting credentials in `.env.example`.
- Presenting illustrative landing-page visuals or N/A risk cards as measurements.
- Treating passing synthetic tests as evidence of real satellite processing.
- Validating a nested ORM relationship through a Pydantic `from_attributes` model that contains PostGIS columns (produced a 500); convert geometry explicitly.
