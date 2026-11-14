# Project status

Last updated: 2026-11-14. Canonical for *current verified state*. Labels: NOT_STARTED, IN_PROGRESS, PARTIALLY_COMPLETED, COMPLETED, BLOCKED, NOT_VERIFIED.

## Phase summary

| # | Phase | Status | Evidence / gap |
|---|---|---|---|
| 1 | Project Foundation & Architecture | COMPLETED | Backend + DB + dashboard + Docker + tests + docs. Includes the cinematic landing page. |
| 2 | Satellite Data Acquisition | PARTIALLY_COMPLETED | Code, migration, API, CLI, UI, docs complete and mock-tested. **No authenticated login and no real file download has ever been performed.** |
| 3 | SAR Image Processing & InSAR Analysis | PARTIALLY_COMPLETED | `SYNTHETIC_PIPELINE_VERIFIED`; **`REAL_DATA_VALIDATION: NOT_PERFORMED`**. No unwrapping, SLC interferometry or Sentinel-1 processing. |
| 4 | Environmental & Geospatial Data Integration | PARTIALLY_COMPLETED | Implemented (incl. the completion addendum: stack manifest, common reference grid, SMAP, user-provided lithology/NDVI/distance layers, clipped soil/land-cover maps, optional IMERG half-hourly) and verified on **synthetic data only**, including a live container run. **`REAL_DATA_VALIDATION: NOT_PERFORMED`**: no real dataset has been processed; every new dataset is `IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA`; nothing is `IMPLEMENTED_AND_TESTED`. |
| 5 | Computer Vision & Feature Extraction (+ labelled dataset) | PARTIALLY_COMPLETED | Implemented and verified on **synthetic data only** (`services/features_cv/`, [ADR-0007](../adr/ADR-0007-feature-extraction-and-labelled-dataset.md)); 106 new tests, live container run 2026-11-14. **`REAL_DATA_VALIDATION: NOT_PERFORMED`**; per-point dynamic features deferred to Phase 6; change features NOT_AVAILABLE until two dated real inputs exist. No ML. |
| 6-10 | Time Series ... Testing & Deployment | NOT_STARTED | No code. |

ML track (separate, [ADR-0009](../adr/ADR-0009-ml-development-track.md)): M0 IN_PROGRESS (workspace done, awaiting dependency-list approval); no model, no data, no result. Details: [ML_STATUS](../ml/ML_STATUS.md).

Current phase: **5** (implemented on synthetic data; awaiting real-data verification of Phases 2-5). Last completed task: Phase 5, 2026-11-14. Next: [NEXT_STEPS.md](NEXT_STEPS.md). Phase 6 does not start without the user's authorization.

## Components

| Component | Status | Notes |
|---|---|---|
| FastAPI app, layering, error envelope, health/system | COMPLETED | |
| Landing page (`/`): cinematic hero + About, Services (status chips), Contact (mailto, placeholders), Footer, nav, reveal transitions | COMPLETED (frontend only, illustrative visuals) | see [CINEMATIC.md](../CINEMATIC.md); contact email/GitHub are placeholders; real-device and cross-browser checks not done |
| Migrations `0001`-`0005` | COMPLETED | `alembic check`: no drift; round-trip 0005 -> 0004 -> 0005 and check verified on the throwaway database (2026-11-14) (`0005` applied in the live container; adds `temporal_kind`, `aligned_file_path`, `reference_grid`) |
| Phase 2 pipeline (auth, providers, downloads, validation, API, CLI, UI) | PARTIALLY_COMPLETED | anonymous catalog search verified live; downloads mock-only |
| Phase 3 InSAR (adapters, processing, runs, `/insar`, `/dashboard/insar`) | PARTIALLY_COMPLETED | synthetic only; sign convention unverified |
| Phase 4 raster utilities, DEM terrain (Horn slope, circular aspect) | COMPLETED (synthetic) | numerical oracles; metre cell sizes on geographic grids |
| Phase 4 rainfall (IMERG daily AOI series, monthly/rolling) | COMPLETED (synthetic) | file layout/units unverified from official sources |
| Phase 4 soil + land cover (local files, statistics, official legend, clipped map rasters) | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | statistics and clipped native-grid maps; download proposals only (no download automation) |
| Phase 4 SMAP soil moisture (SPL3SMP_E, AOI daily series, AM/PM) | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | synthetic only; HDF5 attribute names for units/fill unverified ([SMAP_METHODOLOGY](../scientific/SMAP_METHODOLOGY.md)) |
| Phase 4 user-provided lithology, NDVI, distance to river/fault/road | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | files placed in `data/external/`; GeoJSON-only vectors ([EXTERNAL_LAYERS](../scientific/EXTERNAL_LAYERS.md)) |
| Phase 4 IMERG half-hourly (optional, `rainfall_resolution=half_hourly`) | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | daily stays the default; file layout partly unverified |
| Phase 4 reference grid, alignment and stack manifest (REFERENCE_GRID, MANIFEST stages, `/areas/{id}/manifest`) | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | 16-stage pipeline; [ADR-0006](../adr/ADR-0006-stack-manifest-and-reference-grid.md), [REFERENCE_GRID](../scientific/REFERENCE_GRID.md) |
| Phase 4 catalog reuse, USGS seismic (explicit refresh), InSAR eligibility | COMPLETED (synthetic) | USGS tested with a fake HTTP session only |
| Phase 4 pipeline, quality reports, `/api/v1/environmental/*`, `/dashboard/environmental` (incl. Manifest tab) | COMPLETED (synthetic) | live container + headless-browser check done |
| Docker Compose | COMPLETED | all three healthy after Phase 4 (2026-11-14) |
| Phase 5 feature extraction (local relief, TRI, Laplacian curvature, slope break, lineament density, GLCM texture on a block grid), registry, versioned schema, `ModelInputSpec`, normalisation records, COG/Parquet/NumPy exporters | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | oracle tests on analytic surfaces; parameters (windows, Canny, texture levels) untuned; [FEATURE_EXTRACTION](../scientific/FEATURE_EXTRACTION.md) |
| Phase 5 change features (NDVI difference, coherence change, velocity gradient) | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | behind a refusal guard (two dated REAL inputs); always NOT_AVAILABLE with the Phase 4 stack (one layer per type) |
| Phase 5 labelled sample dataset (EVENT + BACKGROUND samples, stratified background, spatial-block and temporal splits, leakage checker, reserved dynamic columns) | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | synthetic events only; `location_accuracy` parsing NOT_VERIFIED; [LABELLED_DATASET](../scientific/LABELLED_DATASET.md) |
| Phase 5 API `/features-cv` (3 GET routes), CLI `python -m app.services.features_cv` | COMPLETED (synthetic) | read-only; no migration, no DB table (files + manifest) |
| Time series, risk, uncertainty, XAI | NOT_STARTED | Phases 6-8 |
| Any ML/DL model | NOT_STARTED, deferred | [ADR-0002](../adr/ADR-0002-ml-deferral.md) |
| CI pipeline, Playwright e2e tests | NOT_STARTED / UNKNOWN | none found |

## Latest verified test results (2026-11-14)

**After Phase 5 (latest).** Baseline measured BEFORE any Phase 5 code: backend 493 passed / 4 skipped, `alembic check` clean, frontend tsc/lint clean, vitest 87 passed (8 files), build ok. After Phase 5: backend `pytest` on the throwaway database `precursor_t_p5` (Earthdata variables unset): **599 passed, 4 skipped** (493 + 106 new in `tests/features_cv`: terrain 15, tiling/texture/change/registry/schema 30, pipeline 14, dataset 41 (parametrised cases counted), API/CLI/ML-boundary 6); `alembic check` clean (no migration added; head still 0005); frontend `tsc --noEmit` clean, vitest **87 passed in 8 files**, build passes (no frontend change). Docker: backend image rebuilt by the user with scikit-image 0.26.0, scipy 1.18.1, pyarrow 26.0.1; inside the container (Python 3.12.16) imports work, the registry loads, torch/cv2/sklearn are absent, `/api/v1/health` ok, `GET /features-cv/schema` served. **Image size 923 MB -> 1.46 GB (+537 MB).**

Phase 5 live container run (**SYNTHETIC** temporary data: a 512 x 512 grid at 30 m, EPSG:32650, 12 fabricated catalog events inserted for the check; all files and DB rows deleted afterwards, cleanup verified: 0 events, 0 areas, no directories left): `extract` finished in 12.2 s with peak child RSS ~270 MB, 17 features DONE and 3 NOT_AVAILABLE (the change features); `dataset` (seed 7, ratio 2, block 3000 m) finished in 6.6 s: 12 events in, 10 used, 2 excluded (`accuracy_unknown` 1, `accuracy_unparseable` 1), 20 of 20 background samples, 30 rows x 45 columns, leakage `ok: true`, gap 2000 m; the dynamic columns were all null; both read-only API routes returned the same content (`real_data_validation: NOT_PERFORMED`, `contains_synthetic_data: true`). Not measured: memory/time on a multi-million-pixel grid.

Earlier results (after the Phase 4 completion addendum) (backend, frontend, Alembic, Docker): backend `pytest` on the throwaway database `precursor_t_p3` (Earthdata variables unset): **493 passed, 4 skipped** (3 manual live Earthdata + 1 manual real-InSAR); by area: `tests/environmental` **244**, `tests/insar` **92**, `tests/data_acquisition` **142**; `alembic current` = 0005, `alembic check` clean; frontend `tsc --noEmit` clean, `npm run lint` (it runs `tsc --noEmit`) clean, `vitest` **87 passed in 8 files** (this count includes a `landing.test.ts` that was not created by this work), `npm run build` passes and lists `/dashboard/environmental` and `/dashboard/insar`; Docker: backend, frontend and postgres healthy, `/api/v1/health` ok. A live container run with temporary SYNTHETIC data and a headless-Chrome check of the Manifest tab were done earlier the same day (data deleted afterwards).

Addendum live container run (**SYNTHETIC** temporary data, deleted afterwards): reference grid EPSG:32650 at 30 m (34x31); manifest with 17 entries (13 raster, 2 series, 2 vector; 10 static, 7 dynamic), 11 available / 6 not available; road vectors absent so `DISTANCE_ROAD` is NOT_AVAILABLE and the run is PARTIAL; a rerun skipped unchanged stages; a planted 30-degree plane gave mean slope 30.0; missing rainfall and SMAP days are `null`; the Manifest tab rendered with no console or network errors (headless browser, live backend). Backend and frontend images rebuilt, migration `0005` applied, containers healthy. Test data live in `backend/tests/environmental` (all synthetic).

Results below are from the earlier Phase 4 implementation run (before the addendum) and are kept as history:

| Check | Result |
|---|---|
| Backend `pytest` (throwaway PostGIS DB, Earthdata creds unset) | **386 passed, 4 skipped** (3 manual live Earthdata + 1 manual real-InSAR). By area: Phase 4 `tests/environmental` **137**, Phase 3 `tests/insar` **92**, Phase 2 `tests/data_acquisition` **142**, remainder Phase 1 and cross-cutting |
| `alembic check`; `0004` upgrade/downgrade/upgrade | no drift; OK |
| Frontend `tsc --noEmit` / `npm run lint` | clean / clean |
| Frontend `vitest` | **68 passed** (6 files) |
| Frontend `npm run build` | passes; `/dashboard/environmental` and `/dashboard/insar` present |
| Docker (after Phase 4; user restarted Docker Desktop) | backend, frontend, postgres **healthy**; migration `0004` applied on start; rasterio (GDAL 3.12.2) and pandas import in the image; `GET /environmental/datasets` works; frontend image rebuilt with `recharts` |
| Live container run, **SYNTHETIC** DEM + 9 of 10 IMERG-like days + soil + land cover (temporary demo data, removed afterwards) | stages DEM/TERRAIN/SOIL/LAND_COVER DONE, RAINFALL PARTIAL, catalog/seismic/InSAR NOT_AVAILABLE; run PARTIAL; planted 30-degree plane gave mean slope 30.0; missing rainfall day `null` (not zero); raster/preview/legend endpoints 200; second run SKIPPED all five data stages; quality `real_data_validation: NOT_PERFORMED` |
| Headless Chrome on all six `/dashboard/environmental` tabs (live backend, synthetic data) | rendered, no console or network errors; synthetic banners, rainfall gap shown as missing, raster overlay drawn inside the AOI outline |
| Live anonymous CMR (Phase 2) | worked earlier today |
| Any real file: Earthdata login, download, validation, InSAR or environmental processing; live USGS call | **never performed** |

All Phase 3 and Phase 4 test data are synthetic and labelled; passing says nothing about real-data correctness.

## Known bugs and blockers

Blocker: any real result needs an AOI, the user's approval of specific downloads and files.

Phase 2 open issues: (1) `POST /landslide-events/import` with `file_path` reads any server-visible path; (2) `POST /downloads` does not pre-check credentials; (3) storage walk caps at 50,000 files; (4) `UNAVAILABLE` status never set; (5) provider file naming omits the date prefix with `dest_dir`; (6) ASF provider has no explicit timeout and reports `name=NISAR`; (7) `retry_job` does not reset attempts; (8) three CLI tests fail if real Earthdata credentials are in the environment; (9) landslide catalog date order assumed; (10) NISAR HDF5 identification keys and GPM half-hourly/monthly mapping unverified; (11) no git commits.

Phase 3 open issues: (13) NISAR HDF5 layout unverified; (14) phase sign convention and "unwrapped, differential" assumption unverified; (15) Sentinel-1 not processable; (16) GSLC pair interferogram/coherence estimation not wired, two statuses never entered; (17) velocity is a single-interferogram mean; (18) single in-process worker, runs lost on restart; (21) container processing verified only with a synthetic file.

Phase 4 open issues:
22. IMERG daily file layout, units, fill value and time convention **unverified** from official sources (pages would not render); the reader discovers variables by name and refuses ambiguous axes.
23. NASADEM void value (-32768), EGM96 datum and `.zip` packaging are assumptions; `.hgt`/`.zip` synthetic fixtures carry no embedded synthetic tag (labelled only by name). No vertical datum handling.
24. USGS: epoch-millisecond time and km depth not stated on the fetched pages; no numeric rate limit found; HTTP 400 on later pages keeps results and warns; live API never called in tests.
25. SoilGrids CRS/nodata/URLs/file naming and WorldCover nodata/tile naming unverified; no download automation (proposals only). Soil and land cover now also write clipped map rasters (synthetic-tested).
26. AOIs crossing the antimeridian are refused (a shapely polygon straddling 180 degrees cannot be detected from its bbox: limitation); AOI smaller than one cell uses the touched cell and warns.
27. IMERG half-hourly is optional (`rainfall_resolution=half_hourly`, daily stays default). UNKNOWN: Final file name pattern and interval start/end, 48 files per UTC day (inferred), time as seconds since 1980-01-06 and the 3600x1800 grid (search snippet only), mm/hr units text, fill value, dimension order. Verified: product GPM_3IMERGHH V07, 0.1 degree, `precipitation`. Monthly sums use the full calendar month.
28. Single in-process worker for environmental runs too; stale runs fail at restart.
29. `pandas` is used but not pinned in `requirements.txt` (it arrives via xarray); pinning it would force a slow Docker dependency rebuild.
30. Frontend: the overview does not resume a run already in progress on page load.
31. SMAP (see [SMAP_METHODOLOGY](../scientific/SMAP_METHODOLOGY.md)): UNKNOWN are the HDF5 attribute names for units/fill in real files, whether real latitude/longitude are 2-D or 1-D (both handled), the root attributes for short name/version, and the 36 km grid shape.
32. Reference grid and alignment: centroid-only UTM zone and centroid hemisphere; UTM distortion across zones; large downsampling uses bilinear, not area averaging; a categorical raster with no declared nodata gets the dtype maximum as nodata (EnvError if that is a real class id).
33. User-provided layers: vectors are GeoJSON only (Shapefile/GeoPackage need an approved dependency); MODIS 1 km NDVI specifics and that a user file keeps the MOD13 tags are assumptions (MOD13Q1 v061 facts are verified); the NDVI out-of-range count covers the whole source file; rasters are held whole in memory for external layers.
34. Dev database: its 11 NASA collections discovered in Phase 2 were cleared on 2026-11-14 by an incident (a test run truncated the development database; cause and guard in [PROJECT_MEMORY](PROJECT_MEMORY.md) "Do not repeat"). The dev DB now has 0 collections, 0 areas, 0 acquisitions. They were metadata only and can be restored with the anonymous catalog refresh (`GET /api/v1/data/collections?refresh=true`) when the user wants; no real data was lost.

Phase 5 open issues:
35. All Phase 5 behaviour is verified on synthetic fixtures only. Window sizes, Canny thresholds/azimuths, texture window/levels and `min_valid_fraction` are working defaults with no real-data justification; no feature was compared with an independent reference.
36. `location_accuracy` vocabulary, the `exact` -> 0 m rule and the date order of the real catalog are NOT_VERIFIED (no real catalog file). The 2 x radius background buffer is a documented choice, not a validated separation distance.
37. Per-point dynamic features (rainfall, SMAP, InSAR velocity at t-1/3/7/14/30 d) are deferred to Phase 6: columns reserved, all NOT_AVAILABLE. Background samples have no reference date (Phase 6 decision). Change features are NOT_AVAILABLE because the Phase 4 stack stores one layer per type; `insar_velocity_gradient` was implemented as a spatial gradient of one dated real product (flagged choice).
38. Scale limits: dataset sampling holds per-stratum pixel index lists in memory and checks background candidates against all events (fine for the 16 M-pixel grid cap, untested above a 512 x 512 grid); lineament density runs on the whole raster (Canny hysteresis is not tile-invariant); GLCM texture lives on a block grid and is not sampled per point in dataset schema 1.0.0.
39. Docker: the backend image grew by 537 MB (to 1.46 GB). The Dockerfile installs with `--no-cache-dir`, so any `requirements.txt` change re-downloads every package; a BuildKit pip cache mount was proposed to the user and NOT applied. `backend/tests/` is not in the image (the live check copied `synth.py` into the container by hand).
40. Phase 5 event loader fetches catalog events within a fixed 0.25 degree margin of the AOI (heuristic); the dev database currently holds no catalog events, so no real-catalog run exists.
