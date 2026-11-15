# Changelog

Canonical changelog (one only). Meaningful changes; never lists planned work as done. Dates are when verified.

## [Unreleased]

### Added (displacement forecast, ADR-0011, 2026-11-15)
- Map truth check: forecast grid georeferencing verified (99.8% of estimated pixels on land by DEM, POI on land with an estimate); overlay now uses the true UTM corners (grid is rotated ~0.75 deg vs lon/lat, ~70 m). Found and disclosed: forecast correlates -0.81 with the last observed 12-day change (noise reversal), shown on the page and map. OSM basemap + forecast layer in Workspace map; displacement card on Predictions; ML-track status on Susceptibility page; Portuguese Bend registered as a monitored area (API call, 2026-11-15). Landing team list: Intigham Shumalov, Frontend Developer.
- Pulled Farid145678/NASA_SPACE_APPS 86c9d5c: processed OPERA F16940 stack (70 MB), IMERG csv, scaler, `export_scaler.py` into `data/displacement_forecast/`. `saved_model.py` reruns the author's saved weights without retraining on CUDA and reproduces his forecast.tif (20,184 pixels, identical no-estimate pattern, max diff 0.0016 mm); result in `artifacts/reproduction.json`, shown on the page. One user-approved public read: Copernicus GLO-30 tile N33_00_W119_00 window (tile 7.15 MB, AOI window only) cached as `processed/static_terrain.npz`. Training and benchmark metrics are still the author's, not re-run.
- `ai_engine/time_series/displacement_forecast/`: Farid145678/NASA_SPACE_APPS models ported (MLP/LSTM/GRU/TCN/LSTM-TCN, causal dataset, Kalman/OLS trend baselines, QA masks, OPERA fetchers not run); v3 NISAR/geometry/state-space modules and `pipeline.py` (train, evaluate, forecast; CUDA) added; own CUDA-torch env `.venv-displacement`; 58 synthetic-mechanics tests pass.
- Read-only `GET /api/v1/displacement-forecast/{status,metrics,forecast,images/*,docs/*}` over the copied result bundle `data/displacement_forecast/` (not re-run or reproduced here); 4 backend tests. Dashboard page `/dashboard/displacement` (heatmap, benchmark, figures, limitations) and 6 vitest tests. Labelled research / inferred / not a warning. `ml/` susceptibility track unchanged.
- OPERA DISP-S1 CMR search provider (`ENABLE_OPERA`), 3 tests. Dashboard Satellite Data, Analytics, Alerts and Settings pages now show live API data instead of placeholders (Alerts states that none are issued and why); `system/info` registry lists time_series and displacement_forecast as available.

### Added
- Landing page content: sticky nav with Lenis anchor scrolling, active-section tracking and hash/back-forward support; About, Services (status chips mirroring PROJECT_STATUS), Contact (mailto only; placeholder GitHub/email) and Footer sections; one scroll-reveal transition language; reduced-motion fallback. No new dependencies.

### Changed
- Landing Earth now uses the supplied 59-earth textures (downsized, lazy, with procedural fallback); licence of the pack to be confirmed.
- Hero and chapter copy no longer says AI forecasts risk; page metadata no longer claims risk intelligence. Early prediction is stated as a research goal.

### Added (Phase 7, ML slot, no model)
- `/api/v1/prediction/status|models|susceptibility|trigger` (always `MODEL_NOT_TRAINED` under the default `PREDICTION_BACKEND=none`), `services/prediction/` (`Predictor`, `NullPredictor`, `ModelRegistry`), prediction schemas wrapping the Phase 5 `ModelInputSpec`, `models/` template folder, `PREDICTION_DESIGN.md`, `ML_INTEGRATION.md`; 11 tests (2026-11-15). No dependency added.

### Added / Fixed (Phase 10)
- Fixed: landslide `file_path` import confined to the data root (Phase 2 #1); `POST /downloads` returns 412 `credentials_missing` before queuing (#2); `retry` resets attempts (#7); tests no longer see real Earthdata credentials (#8).
- Added: validation, robustness and security/ops tests (+50 backend tests, 701 total, coverage 94.3 %), `docker-compose.prod.yml`, `.github/workflows/ci.yml`, `scripts/backup.sh`, deployment runbook, user guide, validation report, early-warning validation protocol; `pytest-cov` (dev only).

### Added (Phase 9, frontend)
- `/dashboard/workspace` early-warning workspace (reuses existing panels; AOI GeoJSON upload; series panel; source badges on layers), early-warning views against the Phase 7/8 contracts: N/A by default, labelled MOCK mode behind `NEXT_PUBLIC_USE_MOCK_PREDICTIONS` (default off, separate seeded module, neutral palette, no export), real-response path tested with TEST_FIXTURE; Predictions and Susceptibility Map pages now use it; 20 new vitest tests (107 total). No dependency added; no backend change.

### Added (Phase 6, synthetic data only)
- `/api/v1/timeseries/areas/{id}/series[/{zone}/{kind}/analysis]`, `services/timeseries/` (series store with mixed-geometry guard, limitations report, OLS/Theil-Sen/Mann-Kendall/velocity-change/acceleration, antecedent sums, API, wet spells, lagged correlation, `NotImplementedForecaster`), `TIME_SERIES_METHODOLOGY.md`, ADR-0010; 21 tests (2026-11-15). No dependency added (scipy already pinned); no forecast.

### Fixed (Phases 7-8 review, 2026-11-15)
- Prediction service rescans `models/` per request (a stale registry missed folders added at runtime); ledger skipped-layer message. Full backend suite 630 passed on a throwaway database.

### Added (Phase 8, interfaces, no model)
- `GET /api/v1/uncertainty/areas/{id}/report` (data-quality ledger; predictive uncertainty always `NOT_ESTIMATED`), `POST /api/v1/prediction/explain` (`MODEL_NOT_AVAILABLE` without an explainer), `services/uncertainty/` (masks, Cramer-Rao propagation, reliability rules), `Explainer` protocol and `explainer.json` registry support, `UNCERTAINTY_AND_RELIABILITY.md`; 16 tests (2026-11-15). No dependency added.

### Added (ML track, M2)
- `ml/scripts/m2_acquire.py`, `m2_verify.py`, `ml/tests/test_m2_acquisition.py`, `ml/reports/M2_acquisition.md`; 35 approved files (0.79 GB) in `data/ml/raw/` with SHA-256 manifest. IMERG (HTTP 403) and SGMC (size unmeasurable) pending user decisions.

### Added (ML track, M5b)
- `ml/reports/M5b_label_source_proposal.md`, `ml/scripts/m5b_inventory_probe.py` (count-only), M5 user decisions in `docs/ml/ML_STATUS.md` and `docs/ml/stages/M6.md`, candidates in `DATASET_LOG.md`. Proposal only: no download, no new dependency, no model.

### Added (ML track, M5)
- Sealed provisional spatial hold-out (`ml/src/precursor_ml/m5_split.py`, `ml/scripts/m5_seal.py`, `data/ml/splits/m5_provisional_holdout_v1/`), train-only data access (`m5_data.py`), EDA (`m5_eda.py`, `ml/scripts/m5_eda.py`, `ml/notebooks/M5_eda.ipynb`), `ml/tests/test_m5.py`, `ml/reports/M5_eda.md`, figures in `ml/reports/figures/m5/`; M4 dataset `m4-v2` (10 km-capped background buffers primary, imprecise-circle flag, unknown-trigger sensitivity set). No new dependency, no download, no model.

### Added (ML track, M4)
- Data cleaning and QC: `ml/src/precursor_ml/m4.py`, `ml/scripts/m4_clean.py`, `ml/configs/m4_cleaning.yaml`, `ml/tests/test_m4_cleaning.py`, `ml/reports/M4_cleaning.md`; hashed cleaned dataset `m4-v1` (5 km and 10 km) in `data/ml/processed/m4/`. No new dependency, no download.

### Added (ML track, M2b/M3b)
- Round 2 data (771 files, 3.57 GB: HydroRIVERS NA, USGS Qfaults, SoilGrids 12 layers, VIIRS NDVI 2013-2017) in `data/ml/raw/` with `manifest_round2.json`; `ml/scripts/m2b_acquire.py`, `ml/src/precursor_ml/m3b.py`, `ml/scripts/m3b_process.py`, `ml/tests/test_m3b.py`, `ml/reports/M2b_acquisition.md`; 30 new factor bands on the 5 km and 10 km grids. Bulk density not acquired (HTTP 404 tiles). No new dependency.

### Added (ML track, M3 follow-up)
- 10 km sensitivity grid (`m3_preprocess.py --cell-m`, `data/ml/interim/m3_10km/`, one test) and the round 2 download proposal `ml/reports/M3b_round2_proposal.md` (no download, no new dependency).

### Added (ML track, M3)
- `ml/src/precursor_ml/m3.py`, `ml/scripts/m3_preprocess.py`, `ml/configs/m3_study.yaml`, `ml/tests/test_m3_preprocessing.py`, `ml/reports/M3_preprocessing.md`; derived products in `data/ml/interim/m3/` (5 km UTM grid, 43 factor bands, GLC labels with accuracy radii). No new dependency, no download.

### Added (ML track, M2 complete)
- IMERG monthly Final V07 2001-06..2017-12 (199 files) added to `data/ml/raw/`; M2 totals 237 files / 4.58 GB, all checksummed. `m2_verify.py` now checks HDF5 signatures.

### Changed (docs)
- GLC end date corrected to 2017-09-28 in `docs/scientific/{LABELLED_DATASET,SCIENTIFIC_LIMITATIONS,ENVIRONMENTAL_DATA_SOURCES}.md`, `docs/phases/PHASE_07.md`, `docs/project/PROJECT_MEMORY.md` (`docs/data-storage.md` intentionally unchanged).

### Changed (code text, tests)
- Global Landslide Catalog end-date strings corrected to 2017-09-28 in backend code and tests (text only; version identifier `export-2016-03-07` unchanged); new regression test `backend/tests/test_glc_end_date.py`. Backend suite 601 passed / 4 skipped (2026-11-15, Earthdata credentials unset).
- ML M2: USGS per-state geology (CA, OR, WA; 45.6 MB) added as the lithology source; IMERG monthly range extended to 2001-06..2017-12 (pending a GES DISC authorisation).

### Changed (docs)
- Global Landslide Catalog end date corrected to 2017-09-28 in `docs/nasa-data-sources.md`, `docs/phase-2-data-acquisition.md`, `.claude/rules/scientific-integrity.md` (evidence: `ml/reports/M1_census_and_download_list.md`); code constants and tests unchanged.

### Added (ML track, M1)
- M1 label census: `ml/scripts/m1_census.py`, `m1_candidate_coverage.py`, `ml/reports/M1_census_and_download_list.md`; two label files (10.1 MB) in `data/ml/raw/census/`. Download list awaits user approval.
- `ml/reports/M1_problem_definition.md`, `M1_feasibility.md`, `M1_literature.md`, `ml/scripts/m1_catalog_probe.py` (catalog queries only; no download, no model). Study design awaiting user approval.

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
- ML environment installed in `ml/.venv` (approved list, pinned in `ml/requirements.txt`); xgboost uses CUDA (verified), lightgbm is CPU-only; PyTorch deferred to M7. Backend dependencies unchanged.
- `ml/.venv` LightGBM replaced by a local CUDA build of 4.6.0 (patch and recipe in `ml/build/lightgbm_cuda_win/`); GPU training verified. Backend dependencies unchanged.
