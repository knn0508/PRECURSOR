# API documentation

Base: `/api/v1`. Interactive: `/docs` (Swagger), `/openapi.json`. Errors: `{"error": {"code", "message", "details?"}}`. Endpoints below were read from the router code on 2026-11-14. Request/response models: `backend/app/schemas/`.

## Phase 1

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | status, DB connectivity (`degraded` if DB down) |
| GET | `/system/info` | name, version, environment, module registry |
| GET | `/areas`, `/areas/{id}` | list / get monitored areas |
| POST | `/areas` | create area (GeoJSON Polygon/MultiPolygon, 4326) |
| GET | `/acquisitions` | Phase 1 `satellite_acquisitions` metadata |

## Phase 2 (`/data`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/data/collections`, `/data/collections/{id}` | verified collections (`?refresh=true` re-queries CMR) |
| POST | `/data/search` | search NISAR granules only (route calls the NISAR provider; environmental data uses `/data/environmental/acquire`); `dry_run` writes nothing; results are `metadata_only` |
| GET | `/data/acquisitions`, `/data/acquisitions/{id}` | registered granules |
| POST | `/data/downloads` | queue jobs (202), returns `DownloadCreateResponse` (needs Earthdata credentials at run time; not pre-checked) |
| GET | `/data/downloads`, `/data/downloads/{id}` | job list / state |
| POST | `/data/downloads/{id}/retry` | retry a `FAILED` job (202) |
| POST | `/data/environmental/acquire` | NASADEM/IMERG/SMAP for an AOI; `dry_run` defaults true |
| GET | `/data/landslide-events` | catalog events (response carries `limitations`) |
| POST | `/data/landslide-events/import` | import catalog (known issue: `file_path` reads any server path) |
| GET | `/data/status` | provider/credential/storage/job summary; never returns secrets |

Result `data_kind`: `metadata_only` | `downloaded` | `validated`. Maturity: `VALIDATED` | `PROVISIONAL` | `BETA`.

## Phase 3 (`/insar`)

Never downloads, never needs credentials, accepts no filesystem path (inputs are an acquisition id or a bare file name in `data/samples/insar`).

| Method | Path | Purpose |
|---|---|---|
| GET | `/insar/products` | local processable files (downloaded Phase 2 acquisitions + samples); empty until a file exists |
| GET | `/insar/products/{id}`, POST `/insar/inspect` | inspection report (id = acquisition uuid or `sample:<file>`) |
| POST | `/insar/processing-runs` | create + queue a run (202; 200 with `created=false` if an identical run exists; `force` to rerun) |
| GET | `/insar/processing-runs`, `/{id}`, `/{id}/status`, `/{id}/quality` | list (status filter, pagination), detail with products, status, quality report |
| POST | `/insar/processing-runs/{id}/cancel` | cancel (409 if finished) |
| GET | `/insar/deformation-products`, `/{id}` | derived rasters (filters: type, run) |
| GET | `/insar/deformation-products/{id}/raster` | the GeoTIFF/COG, by id only, restricted to `data/processed/insar` |
| GET | `/insar/deformation-products/{id}/preview` | quick-look PNG (diverging scale, `vmax` optional, nodata transparent) |

Run statuses: PENDING, QUEUED, INSPECTING, PREPROCESSING, INTERFEROGRAM_GENERATION, PHASE_UNWRAPPING, DISPLACEMENT_CALCULATION, QUALITY_CHECK, COMPLETED, FAILED, CANCELLED, BLOCKED_MISSING_INPUT (INTERFEROGRAM_GENERATION and PHASE_UNWRAPPING exist in the enum but are never entered: not wired). Every product carries `data_origin` and a label; synthetic data is labelled "SYNTHETIC TEST DATA".

## Phase 4 (`/environmental`)

Never downloads source datasets, accepts no filesystem path, returns no score or prediction. The only outbound call is the explicit seismic refresh.

| Method | Path | Purpose |
|---|---|---|
| GET | `/environmental/datasets` | datasets with honest implementation status |
| GET | `/environmental/layers` | all layers (filters: layer_type, area_id; pagination) |
| GET | `/environmental/areas/{id}/layers` | newest layer per type |
| GET | `/environmental/areas/{id}/manifest` | stack manifest (`ManifestRead`): reference grid plus one entry for every layer kind (raster/series/vector, static/dynamic, status, units, CRS, resolutions, coverage, provenance, `lineage_hash`, file name only; never-processed = NOT_RUN/NOT_AVAILABLE with a reason). Same content as `data/processed/environmental/<area_id>/features/manifest.json`. Design: [ADR-0006](../adr/ADR-0006-stack-manifest-and-reference-grid.md) |
| GET | `/environmental/areas/{id}/coverage` | per layer type: available / status / valid % / reason when missing; missing datasets |
| POST | `/environmental/areas/{id}/process` | queue a run (202); body: stages, force, start/end date, rolling windows, include_insar, `grid_crs` (EPSG:nnnn, projected, metres), `grid_resolution_m` (default 30), `rainfall_resolution` (`daily` default | `half_hourly`); 409 if a run is active |
| GET | `/environmental/processing-runs`, `/{id}`; POST `/{id}/cancel` | run list, stage history, cancel |
| GET | `/environmental/areas/{id}/terrain`, `/soil`, `/land-cover`, `/features` | descriptive features (NOT_AVAILABLE with empty values when not processed) |
| GET | `/environmental/areas/{id}/rainfall` | daily/monthly/rolling series; null = not observed (never zero) |
| GET | `/environmental/areas/{id}/historical-landslides`, `/seismic` | GeoJSON inside the AOI + limitation text |
| POST | `/environmental/areas/{id}/seismic/refresh` | explicit user action: anonymous USGS query for the area bbox; stores new records, reports duplicates; 502 on upstream error |
| GET | `/environmental/areas/{id}/quality-report` | latest run report (passed/failed checks, warnings, missing datasets, `real_data_validation: NOT_PERFORMED`) |
| GET | `/environmental/layers/{id}/raster`, `/preview`, `/legend` | GeoTIFF / PNG (nodata transparent) / legend with the exact colour ramp (`colors` in `LegendRead`, so the legend matches the preview PNG); confined to `data/processed/environmental` |

New layer types (addendum): `SMAP_SOIL_MOISTURE` (series), lithology, NDVI, `DISTANCE_RIVER`/`DISTANCE_FAULT`/`DISTANCE_ROAD`, one soil layer per property/depth; layers are keyed by (`layer_type`, `dataset_name`). NOT_AVAILABLE layers carry the label "No data available for this layer (this is not a zero value)".

Verification (Phase 4): TestClient integration tests on synthetic data (see PROJECT_STATUS); no live USGS call and no real dataset.

## Phase 5 (`/features-cv`)

Read-only (three GET routes; a test asserts no write or process route exists). Extraction and dataset runs are CLI/service only (`python -m app.services.features_cv extract|dataset --area-id <uuid>` from `backend/`). Never exposes file paths; 404 `not_found` until the output exists. No score, probability or prediction anywhere.

| Method | Path | Purpose |
|---|---|---|
| GET | `/features-cv/schema` | versioned feature catalogue (`FeatureSchemaRead`): schema versions, code version, extractors, every `FeatureSpec` (units, window, source layers, static/dynamic). No data needed |
| GET | `/features-cv/areas/{id}/features/manifest` | `data/processed/features/<area_id>/manifest.json` (`FeaturesManifestRead`): grid, parameters, SHA-256 of the Phase 4 manifest, per-feature status/statistics/array hash, NOT_AVAILABLE reasons, synthetic flag, `real_data_validation: NOT_PERFORMED` |
| GET | `/features-cv/areas/{id}/datasets/summary` | summary of the labelled sample dataset (`DatasetSummaryRead`): counts, exclusions by reason, class balance per split, leakage report, lead-time anchors, reserved dynamic columns (NOT_AVAILABLE), caveats, warnings |

Methods: [FEATURE_EXTRACTION](../scientific/FEATURE_EXTRACTION.md), [LABELLED_DATASET](../scientific/LABELLED_DATASET.md). Decision: [ADR-0007](../adr/ADR-0007-feature-extraction-and-labelled-dataset.md). Verified with TestClient on synthetic data and live in the container (2026-11-14).

## Phase 7 (`/prediction`, ML slot, no model)

| Method | Path | Notes |
|---|---|---|
| GET | `/prediction/status` | `{backend, status, registered_models, refused_models, message}`; `status` is `MODEL_NOT_TRAINED` unless a registered model with an attached predictor exists |
| GET | `/prediction/models` | `{registered: [...], refused: [{path, reason}]}` from `models/<id>/<version>/metadata.json` |
| POST | `/prediction/susceptibility`, `/prediction/trigger` | body `{area_id, reference_time?, horizon_days?}`; HTTP 200 `{status: "MODEL_NOT_TRAINED", output: null}` under the default `PREDICTION_BACKEND=none`; HTTP 422 if the area's feature manifest is missing or incompatible with the model's `input_spec` |

| POST | `/prediction/explain` | body `{area_id, head, scope: global|local, cell?}`; HTTP 200 `{status: "MODEL_NOT_AVAILABLE", explanation: null}` unless a registered model has an attached explainer (Phase 8) |
| GET | `/uncertainty/areas/{id}/report` | Phase 8 data-quality ledger (`UncertaintyReport`) from the area's features manifest; `predictive_uncertainty` is always `NOT_ESTIMATED`; 404 if no feature run exists |

Contract and how a model plugs in: [ML_INTEGRATION](ML_INTEGRATION.md); quality rules: [UNCERTAINTY_AND_RELIABILITY](../scientific/UNCERTAINTY_AND_RELIABILITY.md). Verified with TestClient only (2026-11-15); no model exists.

## Phase 6 (`/timeseries`, read-only)

| Method | Path | Notes |
|---|---|---|
| GET | `/timeseries/areas/{id}/series` | metadata of every stored series for the area (kind, zone, sensor, geometry, first/last time, synthetic flag) |
| GET | `/timeseries/areas/{id}/series/{zone}/{kind}/analysis` | limitations report plus indicators (each a result or `NOT_AVAILABLE` with reason); query `alpha`, `gap_factor`, `min_period_days`, `wet_threshold_mm`, `api_k`; 404 if the series is missing, 422 for a bad kind/zone/parameter. No forecast route exists |

Methods: [TIME_SERIES_METHODOLOGY](../scientific/TIME_SERIES_METHODOLOGY.md). Series are written by services/tests, not by the API. Verified with TestClient on synthetic data (2026-11-15).

Verification (Phase 2): mock-tested (TestClient). Live: `/data/collections?refresh=true` and dry-run `/data/search` only (2026-11-14). Everything touching real downloads is NOT_VERIFIED.

## Phase 10 behaviour changes
- `POST /data/downloads`: returns HTTP 412 `{"error": {"code": "credentials_missing", ...}}` before queuing anything when no Earthdata credentials are configured.
- `POST /data/landslide-events/import` with `file_path`: the path must resolve inside the configured data root, otherwise HTTP 422.
- `POST /data/downloads/{id}/retry`: resets `attempts`, `progress` and `bytes_downloaded` to a fresh series.
