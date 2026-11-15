# Next steps

Last updated: 2026-11-14. Canonical for *where to continue*.

## Immediate task: real-data verification of Phases 2, 3, 4 and 5 (needs user input)

Phase 5 is implemented on synthetic data (PARTIALLY_COMPLETED). Phase 6 (time series) was built 2026-11-15 on synthetic data (PARTIALLY_COMPLETED); Phase 9 (workspace) was built 2026-11-15 (PARTIALLY_COMPLETED); Phase 10 was run 2026-11-15 (PARTIALLY_COMPLETED). Phases 2-5 stay PARTIALLY_COMPLETED until real data has been processed.

**Prerequisites (from the user):**
1. A small AOI polygon (create it as a monitored area; <= 5 degrees). Not the Panama test box as a landslide validation site.
2. Explicit approval of a specific download set (file name, source, size). Suggested first set: landslide catalog CSV (few MB); 1-2 NASADEM tiles (~14 MB each); a few IMERG daily files (global, ~tens of MB each); optionally ESA WorldCover tile(s) and SoilGrids GeoTIFFs for the AOI (use the provider `plan_acquisition` proposals, sizes are estimates); **one NISAR GUNW (1.2-2.0 GB)** for Phase 3.
3. Earthdata credentials are in `.env` (do not print them).

**Steps:**
1. Phase 2: `python -m app.cli status/collections`, dry-run discover for the AOI, register, download the approved files only; review manifests.
2. Import the landslide CSV (confirm date order and columns on the real file).
3. Run `POST /api/v1/environmental/areas/{id}/process`; read the quality report and each stage message.
4. Fix reader mismatches found on real files, one regression test per fix: NASADEM `.zip/.hgt` layout, void value and datum; IMERG daily layout, units, fill and time; SoilGrids/WorldCover CRS, nodata and naming; SMAP SPL3SMP_E HDF5 attributes (units/fill, 1-D vs 2-D lat/lon); user-placed lithology, NDVI (scaling tags) and river/fault/road GeoJSON files; IMERG half-hourly (`rainfall_resolution=half_hourly`) layout, units and the 48-interval rule.
4a. Choose the reference grid for the AOI (default: UTM from the centroid at 30 m, or `grid_crs` / `grid_resolution_m`), then read the manifest (`GET /api/v1/environmental/areas/{id}/manifest`) and check units, coverage and lineage per layer.
5. Verify each assumption listed in [ENVIRONMENTAL_DATA_SOURCES](../scientific/ENVIRONMENTAL_DATA_SOURCES.md) and the methodology docs; then, and only then, update dataset statuses (only a real-data pass may use `IMPLEMENTED_AND_TESTED`).
6. Optional explicit action: seismic refresh for the AOI (anonymous USGS query); confirm time/depth units and watch for rate limiting.
7. Phase 3: `REAL_INSAR_FILE=<path> pytest backend/tests/manual/test_real_insar.py -s`; verify sign convention before any claim.
8. Phase 5, after step 4a: `python -m app.services.features_cv extract --area-id <id>` (from `backend/`) and inspect `data/processed/features/<id>/manifest.json`; import the landslide catalog, then `python -m app.services.features_cv dataset --area-id <id> --events-origin REAL_CATALOG`. Check on the REAL catalog: the `location_accuracy` vocabulary (the parser knows unknown/exact/`<n>km`/`<n>m`), the date order, how many events land in `excluded.json`, background shortfall warnings, and whether the 2 x radius buffer leaves room in the AOI. Then review the window/Canny/texture defaults against real terrain and decide which to change (a changed definition is a MAJOR schema bump).
9. Update PROJECT_STATUS, TASK_LOG, CHANGELOG, PHASE_02/03/04/05 tables.

**Required tests:** backend `pytest` stays green (creds unset); `alembic check` clean; a test for every bug fixed.

## Phase 7-8 follow-up (2026-11-15)
Phases 7 and 8 are COMPLETED as contracts/interfaces (630 backend tests passed on a throwaway DB). Remaining, all outside their scope: rebuild the backend Docker image so `/prediction/*` and `/uncertainty/*` are live (user action); Phase 6 (the trigger head has no dynamic inputs until then); when real data exists, record Phase 3 incidence angle, look azimuth and effective looks so the Phase 8 masks and propagation can be fed automatically, then justify mask thresholds on real data; read the original Rodriguez-Martin and Just-Bamler papers. Phase 9 starts only on the user go-ahead.

## Smaller fixes to schedule
Phase 2 issues 1-8; Phase 3 issues 13-18; Phase 4 issues 22-34; Phase 5 issues 35-40 in [PROJECT_STATUS](PROJECT_STATUS.md). Priority: #1 (file_path import) before any deployment; #2; #8 (clear Earthdata env vars in test fixtures). Possible next engineering items: a BuildKit pip cache mount in `backend/Dockerfile` (drop `--no-cache-dir`; proposed, awaiting the user's go-ahead; Phase 5 issue 39), resuming an active run in the overview, pinning pandas when the next dependency rebuild happens, an ADR for installing SNAP/ISCE/SNAPHU before any Sentinel-1 work.

## Housekeeping
Make the first git commit (needs the user's go-ahead). Optional, when the user wants: restore the 11 NASA collections cleared from the dev database by the 2026-11-14 test incident with the anonymous refresh `GET /api/v1/data/collections?refresh=true` (metadata only; no real data was lost).

## Phase 10 pointer (2026-11-15)
All phases are built; validation is what remains. In order: (1) real-data verification of Phases 2-6 (approve a specific download set); (2) decide authentication/rate limiting before any exposure; (3) install Playwright (approved dependency) and write the e2e spec: AOI -> search -> inventory -> job -> layers -> N/A view -> flagged mock view; (4) rebuild both Docker images and run the production profile once; (5) run the CI workflow on a remote; (6) the ML stage, after which the early-warning protocol gets real results. See [PHASE_10](../phases/PHASE_10.md) and [DEPLOYMENT_RUNBOOK](../development/DEPLOYMENT_RUNBOOK.md).

## Phase 9 pointer (2026-11-15)
Phase 9 delivered `/dashboard/workspace` and the early-warning views (N/A default, flagged MOCK mode, real-response path). Do next: rebuild BOTH Docker images (backend for `/timeseries`, frontend for the workspace) and repeat the live check against the containers on :3000 (no CORS workaround needed); consider an AOI drawing control (needs a library decision) and per-date real layers once such rasters exist; decide whether the Inventory/Jobs/InSAR tabs should follow the workspace area. To enable mock mode set `NEXT_PUBLIC_USE_MOCK_PREDICTIONS=true` at build time (default off).

## Phase 6 pointer (2026-11-15)
Phase 6 delivered the series store, indicators, limitations report and forecaster interface (651 backend tests passed on a throwaway DB). Next for Phase 6 once real data exists: build real series from stored Phase 4 rainfall/SMAP outputs and Phase 3 pair products, check the indicator N values and gap factor on them, and decide how to produce per-point dynamic features (gridded rainfall/soil-moisture/velocity series) to fill the Phase 5 `dyn__*` columns. Rebuild the backend image to expose `/api/v1/timeseries/*`.

## Phase 5 / Phase 6 pointer (older)
Phase 5 delivered: versioned feature schema and registry, terrain/texture/change extractors (change features refused without two dated real inputs), the leakage-safe labelled sample dataset (EVENT + BACKGROUND, spatial-block and temporal splits), exporters and a read-only API. Phase 6 will fill the reserved per-point dynamic columns (`dyn__*`, lead-time anchors t-1/3/7/14/30 d) and must decide the reference date of BACKGROUND samples; it starts only when the user authorizes it. Phase 7 owns `services/prediction/` and will validate a model against `ModelInputSpec` (see [FEATURE_EXTRACTION](../scientific/FEATURE_EXTRACTION.md)).

## Blockers
No AOI, no approved download list, no real files.

## Do not change
- Phase 1 schema/endpoints; Phase 2 and Phase 3 migration history (`0001`-`0003`).
- The 10-phase roadmap; default `ALLOWED_MATURITIES=VALIDATED`.
- Labelling rules: synthetic data labelled, `real_data_validation: NOT_PERFORMED` until real data is processed, missing is never zero, environmental and deformation outputs are not risk.
- No ML/DL, no risk scores, probabilities, thresholds or weighted formulas; no unwrapper written from scratch. Phase 5 field names must stay free of score-like words (a test enforces it); BACKGROUND samples are never called negatives.
- opencv and torch stay uninstalled unless the user authorizes them with a written justification.
