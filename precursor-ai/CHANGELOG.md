# Changelog

Canonical changelog (one only). Meaningful changes; never lists planned work as done. Dates are when verified.

## [Unreleased]

### Added
- Landing page content: sticky nav with Lenis anchor scrolling, active-section tracking and hash/back-forward support; About, Services (status chips mirroring PROJECT_STATUS), Contact (mailto only; placeholder GitHub/email) and Footer sections; one scroll-reveal transition language; reduced-motion fallback. No new dependencies.

### Changed
- Landing Earth now uses the supplied 59-earth textures (downsized, lazy, with procedural fallback); licence of the pack to be confirmed.
- Hero and chapter copy no longer says AI forecasts risk; page metadata no longer claims risk intelligence. Early prediction is stated as a research goal.

### Added (docs)
- Project documentation and memory system: `CLAUDE.md`, `.claude/rules/*`, `.claude/skills/precursor-workflow`, `docs/project|architecture|adr|phases|scientific|development`.

### Technical Notes
- Backend 157 passed / 3 skipped (2026-11-14, Earthdata creds unset). Three CLI tests fail if real credentials are in the environment (not fixed).

## [Phase 5] - 2026-11-14 (implemented on synthetic data; no real dataset processed; no ML)

### Added
- `backend/app/services/features_cv/`: raster tiling with halo and recorded normalisation; terrain features (local relief, Riley TRI, Laplacian curvature, slope break, hillshade-Canny lineament density); GLCM texture on a declared block grid; change features (NDVI difference, coherence change, velocity gradient) refused unless two dated REAL inputs share a grid; `FeatureExtractor` protocol and registry; versioned feature schema and `ModelInputSpec` (the contract a future model is validated against); Phase 4 stack loader; extraction pipeline writing COGs and `manifest.json` under `data/processed/features/<area_id>/`.
- Labelled sample dataset builder: EVENT samples from the catalog (unusable events excluded with reasons; `location_accuracy` parsed from `original_attributes`, NOT_VERIFIED), stratified BACKGROUND samples outside `max(2 x radius, min buffer)` of every event, static features sampled per point, reserved all-NOT_AVAILABLE dynamic columns and lead-time anchors (per-point dynamics deferred to Phase 6), spatial-block and temporal splits, leakage checker, Parquet/NumPy exporters and a lazy PyTorch `Dataset` interface (torch not installed). Files under `data/processed/datasets/<area_id>/`.
- CLI `python -m app.services.features_cv extract|dataset --area-id <uuid>`; read-only API `GET /api/v1/features-cv/schema`, `/areas/{id}/features/manifest`, `/areas/{id}/datasets/summary`.
- Docs: [ADR-0007](docs/adr/ADR-0007-feature-extraction-and-labelled-dataset.md), [FEATURE_EXTRACTION](docs/scientific/FEATURE_EXTRACTION.md), [LABELLED_DATASET](docs/scientific/LABELLED_DATASET.md), rewritten PHASE_05, API/structure/dependency docs.
- 106 backend tests in `backend/tests/features_cv` (synthetic; analytic oracles, leakage tests, ML-boundary name scan).

### Dependencies (justified in ADR-0007; pinned in `backend/requirements.txt`)
- `scikit-image==0.26.0`: GLCM texture (`graycomatrix`/`graycoprops`) and Canny edges. `scipy==1.18.1`: `ndimage` focal/Gaussian filters and `cKDTree` for sample spacing and leakage checks (ADR-0005 had rejected scipy because Phase 4 did not need it). `pyarrow==26.0.1`: Parquet export. Not added: opencv-python-headless, torch. Backend image 923 MB -> 1.46 GB.

### Changed
- `ai_engine/computer_vision/README.md` no longer says it flags candidate unstable slopes; it states descriptive extraction only and points to the backend module.
- PROJECT_STATUS splits Phase 5 from Phases 6-10 (Phase 5 PARTIALLY_COMPLETED); ROADMAP row 5 updated.

### Technical Notes
- Backend 599 passed / 4 skipped (493 + 106; Earthdata creds unset; `alembic check` clean, no migration); frontend unchanged: tsc clean, vitest 87 passed, build ok. Live container run on temporary synthetic data (512 x 512 at 30 m): extract 12.2 s / ~270 MB peak, dataset 6.6 s, leakage ok; data deleted afterwards.
- `REAL_DATA_VALIDATION: NOT_PERFORMED`. All parameters (windows, Canny, texture) are untuned working defaults.

## [Phase 4 addendum] - 2026-11-14 (implemented on synthetic data; no real dataset processed)

### Added
- Stack manifest: `GET /api/v1/environmental/areas/{id}/manifest` and `data/processed/environmental/<area_id>/features/manifest.json` (MANIFEST stage); one entry per layer kind (never-processed = NOT_RUN/NOT_AVAILABLE with a reason) with units, CRS, resolutions, static/dynamic, origin and synthetic flag, coverage, provenance and `lineage_hash`. Design: [ADR-0006](docs/adr/ADR-0006-stack-manifest-and-reference-grid.md).
- Migration `0005`: `environmental_layers.temporal_kind` and `aligned_file_path`, `environmental_processing_runs.reference_grid` (JSONB).
- Common reference grid (UTM from the AOI centroid, user CRS allowed, default 30 m) and alignment of every raster layer; stages REFERENCE_GRID and MANIFEST (16 stages in total); process options `grid_crs`, `grid_resolution_m`, `rainfall_resolution`.
- SMAP SPL3SMP_E soil-moisture series (AM/PM, optional quality filter); user-provided lithology, NDVI and river/fault/road distance layers from `data/external/` (GeoJSON-only vectors); optional IMERG half-hourly rainfall; clipped soil and land-cover map rasters. See [REFERENCE_GRID](docs/scientific/REFERENCE_GRID.md), [SMAP_METHODOLOGY](docs/scientific/SMAP_METHODOLOGY.md), [EXTERNAL_LAYERS](docs/scientific/EXTERNAL_LAYERS.md).
- Frontend: Manifest tab, grid CRS/resolution and rainfall-product fields, new layer kinds, server-supplied legend colours, confirmation before seismic refresh.
- Test-safety guard: `backend/tests/conftest.py` refuses DB tests on any database whose name does not start with `precursor_t` (override: `ALLOW_TESTS_ON_ANY_DATABASE=1`).

### Changed
- Soil and land cover write clipped map rasters in addition to statistics. Distance and lithology/NDVI rasters are written on the reference grid.

### Fixed
- `json_safe` converts UUIDs; rainfall per-file warnings collapsed into one counted line; NOT_AVAILABLE layers are labelled as not a zero value; layer `units` column widened to 120 chars (migration `0004`, before release).

### Technical Notes
- No ML, no scores or thresholds, no downloads, no Earthdata login; every new dataset is IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA. Test results: backend 493 passed / 4 skipped (environmental 244, insar 92, data_acquisition 142), alembic check clean at 0005, frontend 87 tests passed (8 files) with tsc/build clean, Docker healthy
- Incident 2026-11-14: tests were pointed at the development database through a one-line `export` pitfall and truncated it (the 11 collections from Phase 2 are gone; metadata only, restorable by the anonymous refresh). Details: [PROJECT_MEMORY](docs/project/PROJECT_MEMORY.md).

## [Phase 4] - 2026-11-14 (implemented on synthetic data; no real dataset processed)

### Added
- Environmental integration `backend/app/services/environmental/`: raster utilities (inspection, clip, mosaic, alignment, quality), DEM terrain (Horn slope with metre cell sizes, circular aspect), IMERG rainfall processing (daily/monthly/rolling, missing never zero), soil and land-cover providers/processors (local files, statistics, official legend), USGS earthquake provider (pagination, retry, de-duplication), historical-landslide and seismic features, InSAR eligibility (real-only features), ten-stage pipeline (extended to 16 stages in the addendum) with NOT_AVAILABLE/SKIPPED semantics, quality reports, previews and legends.
- Migration `0004`: `environmental_processing_runs`, `environmental_layers`, `environmental_features`, `earthquake_events`.
- API `/api/v1/environmental/*` and page `/dashboard/environmental` (map layers, terrain, rainfall charts, events, quality). `recharts` added to the frontend.
- Docs: PHASE_04, ADR-0005, TERRAIN_METHODOLOGY, RAINFALL_METHODOLOGY, ENVIRONMENTAL_DATA_SOURCES.

### Changed
- Provider clip masks cells to the AOI polygon (not only its bbox) and handles an AOI smaller than one cell with a warning.

### Technical Notes
- No ML, no risk scores, no downloads. IMERG layout, NASADEM void/datum, USGS units/rate limit, SoilGrids and WorldCover specifics are unverified. Soil and land cover had no map raster at this point (added in the addendum).

## [Phase 3] - 2026-11-14 (implemented; real-data validation NOT_PERFORMED)

### Added
- InSAR processing in `backend/app/services/insar/`: product-aware adapters (NISAR GUNW, GSLC, GCOV; Sentinel-1 SLC interface), inspection service, LOS displacement from unwrapped phase, coherence validation/statistics, mean LOS velocity with compatibility checks, block-wise processing, COG/GeoTIFF + preview writers, per-run quality reports, controlled external-tool runner (SNAP/ISCE/SNAPHU gate).
- Migration `0003`: `insar_processing_runs`, `deformation_products`.
- API `/api/v1/insar/*` (products, inspect, processing-runs incl. status/quality/cancel, deformation-products incl. raster/preview). Accepts no filesystem path.
- Dashboard page `/dashboard/insar`.
- Settings `INSAR_BLOCK_ROWS`, `INSAR_TIMEOUT_S`, `INSAR_MIN_FREE_DISK_BYTES`; explicit `numpy` requirement.
- Manual test `tests/manual/test_real_insar.py` (skipped unless `REAL_INSAR_FILE`); docs INSAR_METHODOLOGY, DEFORMATION_METRICS, ADR-0004, PHASE_03.

### Changed
- `/system/info` reports `insar` as available (with a not-validated note). `main.py` lifespan also creates the InSAR layout and fails stale runs. `docker-compose.yml` forwards the InSAR settings.

### Fixed
- `backend/Dockerfile` installs `libexpat1`: rasterio could not be imported in the slim image (latent since Phase 2, where it was imported lazily).

### Technical Notes
- Docker image rebuilt by the user with the `libexpat1` fix: stack healthy; one synthetic GUNW processed through the live API and rendered in the browser (demo data removed afterwards).
- All tests use synthetic, labelled fixtures. The NISAR HDF5 layout and the phase sign convention are unverified. No unwrapping, SLC interferometry or Sentinel-1 processing.

## [Phase 2] - 2026-11-14 (implemented; live acquisition NOT_VERIFIED)

### Added
- NASA data pipeline `backend/app/services/data_acquisition/`: providers for NISAR (GUNW, GCOV, GSLC, optional GOFF/SME2, ASF search fallback), NASADEM, GPM IMERG, optional SMAP, Global Landslide Catalog; Earthdata auth service; resumable download manager; file validation; metadata registration; orchestrator.
- Migration `0002`: `data_collections`, `data_acquisitions`, `download_jobs`, `landslide_events` (PostGIS footprints, JSONB metadata, unique provider+granule).
- API `/api/v1/data/*` (13 endpoints) and CLI `python -m app.cli`.
- Dashboard section `/dashboard/data/*` (overview, search, downloads, inventory).
- Settings for Earthdata, data root, maturities, limits, provider toggles; `./data:/data` Docker volume.
- Docs: phase-2-data-acquisition, nasa-data-sources, earthdata-authentication, aoi-configuration, data-storage, data-quality-validation.

### Changed
- `main.py` gained a lifespan (storage layout, recovery of interrupted jobs); `app/core/geo_env.py` fixes PROJ_LIB.
- `.gitignore` covers `.netrc`, credentials, raw data and metadata.

### Fixed
- Alembic drift and index naming in `0002`; circular import (aoi/types).

### Technical Notes
- Live verification limited to anonymous CMR searches. No login, no file downloaded.

## [Phase 1] - foundation

### Added
- FastAPI + SQLAlchemy 2 + GeoAlchemy2 backend; `/health`, `/system/info`, `/areas`, `/acquisitions`; Alembic `0001` (PostGIS, `monitored_areas`, `satellite_sources`, `satellite_acquisitions`).
- Next.js dashboard shell with MapLibre; Docker Compose (postgres, backend, frontend); tests; README and ARCHITECTURE.
- Cinematic scroll-driven landing page (Three.js/R3F, GSAP, Lenis) with static fallback; illustrative visuals only.

### Fixed
- Host DB port moved to 55432; MapLibre worker served statically under Turbopack; landing-page visual defects.

## [ML track M0] - 2026-11-15 (governance and workspace only; no model, no data, no new dependency)
- Added ADR-0009 (isolated ML development track), `.claude/rules/ml.md`, the `ml/` workspace skeleton and scope-guard script, `data/ml/` folders (gitignored), `docs/ml/*` logs and a dependency proposal (not installed). Roadmap phases unchanged and ML-free.
