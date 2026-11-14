# Phase 2: NASA data acquisition

Phase 2 finds, downloads, checks and registers NASA source data for a user-supplied Area of Interest (AOI). It does **no** scientific processing: no InSAR, no change detection, no risk score.

> **Honesty note.** During development only anonymous, read-only NASA catalog (CMR) searches were run against live services. **No NASA data file has been downloaded and no Earthdata login has ever been performed.** The download path is tested with mocks only. See [Verification status](#verification-status).

Related: [nasa-data-sources.md](nasa-data-sources.md) · [earthdata-authentication.md](earthdata-authentication.md) · [aoi-configuration.md](aoi-configuration.md) · [data-storage.md](data-storage.md) · [data-quality-validation.md](data-quality-validation.md)

## Scope

| Source | Provider | Purpose |
|---|---|---|
| NISAR L2 (GUNW, GCOV, GSLC, GOFF) / L3 SME2 | `NISAR` | SAR products (ASF DAAC) |
| NASADEM_HGT | `NASADEM` | Elevation tiles |
| GPM IMERG (Final Run) | `GPM` | Rainfall |
| SMAP L3 soil moisture | `SMAP` | Optional, off by default |
| NASA Global Landslide Catalog | `LANDSLIDE_CATALOG` | Historical point events (not a granule provider) |

## Architecture

```
 CLI (app.cli)  /  REST (/api/v1/data/*)
        |
        +--> AcquisitionSearchService ----> providers (registry.build_providers, per ENABLE_*)
        |        |  AOI size check            NISARDataProvider  (CMR; ASFSearchProvider = search-only fallback)
        |        |  maturity filter           NASADEMDataProvider / GPMDataProvider / SMAPDataProvider
        |        |  per-provider isolation       |  all use cmr.py (earthaccess; anonymous search)
        |        v                               v
        |   MetadataRegistrationService     GranuleRecord (metadata only)
        |        |  upsert data_collections / data_acquisitions (status DISCOVERED)
        |        v
        +--> AcquisitionOrchestrator  (thread pool, MAX_CONCURRENT_DOWNLOADS)
                 |  plan_jobs -> QUEUED -> run_job
                 |  provider.download_granule -> DownloadManager (.part, resume, retry, atomic rename)
                 |       auth: EarthdataAuthenticationService (only here)
                 |  FileValidationService (format-aware checks)
                 v
          data/raw/...  +  data/metadata/{collections,acquisitions}/*.json  +  PostgreSQL rows

 LandslideCatalogProvider: fetch CSV -> import_file -> landslide_events (no auth, no jobs)
```

Code: `backend/app/services/data_acquisition/`. Models: `backend/app/models/{data_collection,data_acquisition,download_job,landslide_event}.py`. Migration: `backend/alembic/versions/0002_data_acquisition.py`. Phase 1 `satellite_acquisitions` is untouched.

## Workflow

1. **Discover collections** (anonymous). Providers ask CMR which collections exist; only confirmed ones are returned and (unless dry-run) upserted into `data_collections`. Missing collections produce warnings, never invented rows.
2. **Search granules** for an AOI + date range (anonymous). Results are metadata only. CMR spatial matching is a superset, so footprints are re-checked with shapely. Unless dry-run, hits are registered as `DISCOVERED`.
3. **Download** registered granules (needs Earthdata credentials). Jobs run in a thread pool; each job downloads, then validates.
4. **Validate** the file (structural checks, see [data-quality-validation.md](data-quality-validation.md)) and write a provenance manifest.

Defaults are conservative: `ALLOWED_MATURITIES=VALIDATED`, at most `MAX_GRANULES_PER_REQUEST=10` granules per request (extras are skipped), AOI bbox at most `MAX_AOI_BBOX_DEGREES=5` degrees, files over `MAX_FILE_SIZE_BYTES` (3 GiB) are refused.

## Acquisition states (`data_acquisitions.status`)

| State | Exact meaning |
|---|---|
| `DISCOVERED` | Row registered from catalog metadata. Nothing downloaded. Re-searching refreshes catalog fields only in this state (and `FAILED`). |
| `QUEUED` | A download job was created and is waiting for a worker. |
| `DOWNLOADING` | A worker is transferring bytes. |
| `DOWNLOADED` | A complete file is on disk (`local_file_path` set); validation has not finished. |
| `VALIDATING` | File checks are running. |
| `VALIDATED` | All file checks passed. **File integrity only, not scientific validation.** |
| `FAILED` | Download or validation failed; `error_message` says why. Retryable. Also set on jobs interrupted by a restart. |
| `SKIPPED` | Not downloaded because the catalog size exceeds `MAX_FILE_SIZE_BYTES`. |
| `UNAVAILABLE` | Defined in the enum and API contract; **no code currently sets it**. |

Transitions: `DISCOVERED -> QUEUED -> DOWNLOADING -> DOWNLOADED -> VALIDATING -> VALIDATED`; any failure -> `FAILED`; `FAILED -> QUEUED` via retry. `plan_jobs` skips granules already `VALIDATED`/`DOWNLOADED`, with an active job, unregistered, or beyond the per-request cap.

## Download job states (`download_jobs.status`)

| State | Meaning |
|---|---|
| `QUEUED` | Created, not started. |
| `RUNNING` | Worker active; `progress` (0..1) and `bytes_downloaded` reflect real bytes, committed at most every 0.5 s. |
| `COMPLETED` | Download and validation both succeeded. |
| `FAILED` | See `error_message`. Only `FAILED` jobs can be retried. |

Executor is in-process (no external queue). `recover_stale_jobs()` marks `QUEUED`/`RUNNING` jobs `FAILED` ("interrupted by restart; retry to resume") because nothing survives a process restart. Whether it is called at app startup is not verified here.

## How to run

Prerequisites: PostGIS running, `alembic upgrade head` applied, dependencies from `backend/requirements.txt`. Run CLI commands from `backend/`.

> The CLI (`backend/app/cli`) and API routers (`backend/app/api/v1/data`) were still being written when this document was authored. Command names and exit codes below come from the intended design; flags are **(see --help)**.

```bash
# 0. Provide an AOI (none ships; see aoi-configuration.md)
ls data/aoi/

# 1. Discover collections (no credentials needed)
python -m app.cli collections            # (see --help) for dry-run vs register

# 2. Dry-run granule search (nothing written to the database)
python -m app.cli discover --aoi ../data/aoi/my_aoi.geojson --start 2025-01-01 --end 2025-03-31 --dry-run   # (see --help)

# 3. Register results (same command without --dry-run), then list
python -m app.cli discover --aoi ../data/aoi/my_aoi.geojson --start 2025-01-01 --end 2025-03-31            # (see --help)

# 4. Download (needs EARTHDATA_USERNAME/PASSWORD or ~/.netrc). Start with ONE granule: GUNW is ~1.4-2 GB.
python -m app.cli download --help
python -m app.cli status

# 5. Environmental data (NASADEM, IMERG, optional SMAP); dry-run by default via the API
python -m app.cli acquire-environmental --help

# 6. Landslide catalog (no credentials)
python -m app.cli import-landslides --help

# Maintenance
python -m app.cli history --help ; python -m app.cli retry --help ; python -m app.cli revalidate --help
```

Equivalent API calls (Swagger at `http://localhost:8000/docs`):

```bash
curl -s localhost:8000/api/v1/data/status
curl -s -X POST localhost:8000/api/v1/data/search -H 'content-type: application/json' -d '{
  "aoi": {"geometry": {"type":"Polygon","coordinates":[[[X1,Y1],[X2,Y1],[X2,Y2],[X1,Y2],[X1,Y1]]]}, "name":"my-aoi"},
  "start_date":"2025-01-01T00:00:00Z", "end_date":"2025-03-31T00:00:00Z",
  "products":["GUNW"], "maturities":["VALIDATED"], "max_results":3, "dry_run":true }'
curl -s -X POST localhost:8000/api/v1/data/downloads -H 'content-type: application/json' -d '{"acquisition_ids":["<uuid from a non-dry-run search>"]}'
curl -s localhost:8000/api/v1/data/downloads/<job-id>
```

Replace `X1..Y2` with your own coordinates. `acquisition_ids` come only from a non-dry-run search.

## CLI

Exit codes: `0` ok, `2` usage/validation error, `3` provider/network error, `4` Earthdata credentials missing.

| Command | Purpose | Auth |
|---|---|---|
| `collections` | Discover/list collections | no |
| `discover` | Search granules for an AOI; `--dry-run` skips registration | no |
| `download` | Create download jobs for registered granules | yes |
| `acquire-environmental` | NASADEM / IMERG / (SMAP) for an AOI and date range | download only |
| `import-landslides` | Fetch and import the Global Landslide Catalog CSV | no |
| `status` | Provider, credential, storage and job summary | no |
| `history` | Past acquisitions/jobs | no |
| `retry` | Re-queue a `FAILED` job | yes |
| `revalidate` | Re-run file checks on an existing local file | no |

Arguments and flags: **(see --help)**.

## API (`/api/v1/data`)

Contract: `backend/app/schemas/data_acquisition.py`. Endpoint list is the intended design; confirm against `/docs`.

| Method | Path | Request -> response |
|---|---|---|
| GET | `/collections` | -> `CollectionRead[]` |
| GET | `/collections/{id}` | -> `CollectionRead` |
| POST | `/search` | `SearchRequest` -> `SearchResponse` (`results`, `warnings`, `provider_errors`) |
| GET | `/acquisitions` | filters: product type, status, maturity, area, dates, offset/limit -> `AcquisitionList` |
| GET | `/acquisitions/{id}` | -> `AcquisitionRead` |
| POST | `/downloads` | `DownloadCreate` (1-50 `acquisition_ids`) -> `DownloadCreateResponse` |
| GET | `/downloads` | -> `DownloadJobList` |
| GET | `/downloads/{id}` | -> `DownloadJobRead` |
| POST | `/downloads/{id}/retry` | -> `DownloadJobRead` (only `FAILED`) |
| POST | `/environmental/acquire` | `EnvironmentalAcquireRequest` (`dry_run` defaults **true**) -> `EnvironmentalAcquireResponse` |
| GET | `/landslide-events` | bbox/AOI/date/country filters -> `LandslideEventList` (carries `limitations`) |
| POST | `/landslide-events/import` | `LandslideImportRequest` -> `LandslideImportResponse` |
| GET | `/status` | -> `DataStatus` |

`AOIInput` takes exactly one of `monitored_area_id` or `geometry`. `SearchRequest.max_results` is 1-100 but is capped by `MAX_GRANULES_PER_REQUEST`. Results carry `data_kind`: `metadata_only`, `downloaded` or `validated`.

## Database schema

Migration `0002`. All geometry is EPSG:4326 (SRID 4326).

### `data_collections`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| provider | varchar(30) | NOT NULL, index |
| collection_short_name | varchar(120) | NOT NULL |
| dataset_name | varchar(300) | NOT NULL |
| product_type | varchar(50) | NOT NULL, index |
| version | varchar(30) | NOT NULL |
| maturity | varchar(20) | NULL for non-NISAR, index |
| description | text | |
| documentation_url | varchar(500) | |
| cmr_concept_id | varchar(60) | |
| metadata_json | JSONB | NOT NULL, default `{}` |
| discovered_at | timestamptz | NOT NULL, default now |

Constraint `uq_collection_name_version` UNIQUE (collection_short_name, version).

### `data_acquisitions`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| monitored_area_id | UUID FK -> monitored_areas | ON DELETE SET NULL, index |
| collection_id | UUID FK -> data_collections | NOT NULL, ON DELETE RESTRICT, index |
| provider, granule_id, product_type | varchar(30) / (300) / (50) | NOT NULL; `granule_id` indexed |
| acquisition_start, acquisition_end, processing_date | timestamptz | |
| orbit_direction | varchar(20) | |
| relative_orbit | integer | NISAR: from `TRACK_NUMBER` |
| spatial_footprint | geometry(GEOMETRY, 4326) | GiST index `idx_data_acquisitions_spatial_footprint` |
| crs | varchar(30) | NOT NULL, default `EPSG:4326` |
| file_format | varchar(30) | |
| file_size_bytes | bigint | |
| download_url | text | |
| local_file_path | text | set when a file lands |
| checksum, checksum_algorithm | varchar(128) / (20) | after download: SHA-256 computed locally |
| maturity | varchar(20) | |
| status | varchar(20) | NOT NULL, default `DISCOVERED` |
| retrieved_at | timestamptz | set when a file lands |
| metadata_json | JSONB | NOT NULL; provider MD5 in `published_checksum` |
| validation_report | JSONB | NOT NULL, default `{}` |
| error_message | text | |
| created_at, updated_at | timestamptz | NOT NULL, default now |

Constraint `uq_acq_provider_granule` UNIQUE (provider, granule_id). Indexes: `ix_dacq_start` (acquisition_start), `ix_dacq_status` (status), `ix_dacq_product_maturity` (product_type, maturity). `status` has no database CHECK; values are enforced in code/schemas.

### `download_jobs`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| acquisition_id | UUID FK -> data_acquisitions | NOT NULL, ON DELETE CASCADE, index |
| status | varchar(20) | NOT NULL, default `QUEUED`; index `ix_djob_status` |
| progress | float | NOT NULL, default 0 (0..1) |
| bytes_downloaded | bigint | NOT NULL, default 0 |
| attempts | integer | NOT NULL, default 0 (incremented per run) |
| error_message | text | |
| started_at, completed_at | timestamptz | |
| created_at, updated_at | timestamptz | NOT NULL, default now |

### `landslide_events`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| external_event_id | varchar(60) | NOT NULL |
| event_date | timestamptz | NULL if unparseable |
| location_name, source | text | |
| country | varchar(100) | index |
| trigger, landslide_type | varchar(100) | |
| geometry | geometry(POINT, 4326) | NOT NULL, GiST `idx_landslide_events_geometry` |
| original_attributes | JSONB | NOT NULL; the full CSV row |
| dataset_version | varchar(60) | NOT NULL (default `export-2016-03-07`) |
| retrieved_at | timestamptz | NOT NULL, default now |

Constraint `uq_event_id_version` UNIQUE (external_event_id, dataset_version). Index `ix_lsevent_date` (event_date). Re-importing the same version upserts.

## Configuration

Set in `.env` (see `.env.example`). Defaults are from `backend/app/core/config.py`.

| Variable | Default | Meaning |
|---|---|---|
| `EARTHDATA_USERNAME` | unset | Earthdata Login user (downloads only) |
| `EARTHDATA_PASSWORD` | unset | Earthdata Login password (downloads only) |
| `DATA_ROOT` | `./data` | Root for raw files and manifests (`/data` in Docker) |
| `AOI_DIR` | `<DATA_ROOT>/aoi` | AOI directory (commented out in `.env.example`) |
| `NISAR_PRODUCTS` | `GUNW,GCOV,GSLC` | Products searched by default; `GOFF`, `SME2` optional |
| `ALLOWED_MATURITIES` | `VALIDATED` | Comma list of `VALIDATED,PROVISIONAL,BETA` |
| `MAX_CONCURRENT_DOWNLOADS` | `2` | Thread-pool size |
| `REQUEST_TIMEOUT_S` | `60` | HTTP timeout per request |
| `DOWNLOAD_RETRIES` | `3` | Retries after the first attempt (4 attempts total) |
| `MAX_FILE_SIZE_BYTES` | `3221225472` | Per-file cap (3 GiB) |
| `MAX_GRANULES_PER_REQUEST` | `10` | Cap on search results and jobs per request |
| `MAX_AOI_BBOX_DEGREES` | `5` | Max AOI bbox width/height in degrees |
| `ENABLE_NISAR` / `ENABLE_NASADEM` / `ENABLE_GPM` | `true` | Provider switches |
| `ENABLE_SMAP` | `false` | Optional provider |
| `ENABLE_LANDSLIDE_CATALOG` | `true` | Catalog importer switch (status reporting) |
| `GPM_RESOLUTION` | `daily` | `daily`, `half_hourly` or `monthly` (anything else raises at provider build, so the provider is skipped) |
| `SMAP_COLLECTION` | `SPL3SMP_E` | SMAP short name |

`docker-compose.yml` passes through only: the two Earthdata variables, `NISAR_PRODUCTS`, `ALLOWED_MATURITIES`, `MAX_CONCURRENT_DOWNLOADS`, `MAX_FILE_SIZE_BYTES`, `MAX_GRANULES_PER_REQUEST`, `ENABLE_SMAP`, `GPM_RESOLUTION`; it sets `DATA_ROOT=/data` and mounts `./data:/data`. Other variables in `.env` are **not** forwarded into the container.

## Testing

```bash
cd backend
pytest tests/data_acquisition            # unit tests, all NASA services mocked
```

- Unit tests use fakes (`tests/data_acquisition/fakes.py`); the CMR seam (`cmr.find_collections` / `cmr.find_granules`), `asf_search` and HTTP sessions are patched. No network.
- DB-backed tests (registration, orchestrator, landslide import) need PostGIS. Set `TEST_DATABASE_URL` to a **throwaway** database: fixtures run `alembic upgrade head` and truncate Phase 1 and Phase 2 tables after every test. Without a reachable database these tests are **skipped**, not passed.

```bash
export TEST_DATABASE_URL=postgresql+psycopg://precursor:<password>@localhost:55432/precursor_test
cd backend && pytest
```

- Manual live test (not yet present in the repo at authoring time: `backend/tests/manual/test_live_earthdata.py`): intended to be run with `RUN_LIVE_EARTHDATA=1`. It would need real Earthdata credentials and downloads real data; read it before running.

```bash
cd backend && RUN_LIVE_EARTHDATA=1 pytest tests/manual/test_live_earthdata.py -s
```

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Exit code 4 / "Earthdata credentials missing or invalid" | Set `EARTHDATA_USERNAME`/`PASSWORD` in `.env` or `~/.netrc`. |
| HTTP 401/403 on download | Wrong password, or NASA application EULA not approved on your Earthdata profile (GES DISC, ASF, NSIDC). See [earthdata-authentication.md](earthdata-authentication.md). |
| "AOI bounding box is ... the limit is 5 degrees" | Use a smaller AOI or raise `MAX_AOI_BBOX_DEGREES` deliberately. |
| "requested maturities ... are not enabled" | Add `PROVISIONAL`/`BETA` to `ALLOWED_MATURITIES`. |
| Warning "no VALIDATED collection exists for SME2" | Expected: SME2 exists only as PROVISIONAL/BETA. |
| Provider missing from results | Disabled via `ENABLE_*`, or failed to load (logged as `provider X unavailable`); check `provider_errors` and `status`. |
| `GPM` provider absent | Invalid `GPM_RESOLUTION`. |
| "refusing to overwrite existing file" | A different file with that name is on disk; move it. Raw files are never overwritten. |
| "not enough free disk space" | Free space for 1.05 x expected size. |
| Job FAILED "interrupted by restart; retry to resume" | Retry; the `.part` file is resumed. |
| `pyproj` / PROJ database errors during validation or tests | A system PostgreSQL/PostGIS `PROJ_LIB` can shadow pyproj's data. Tests work around it with `PROJ_LIB=$(python -c "import pyproj;print(pyproj.datadir.get_data_dir())")`. `app/core/geo_env.py` does not exist in the repo at authoring time, so set this yourself if needed. |
| DB tests skipped | `TEST_DATABASE_URL` unset or database unreachable. |

## Known limitations

- Downloads are untested against live NASA services (see below).
- No scheduler, no external queue: jobs live in an in-process thread pool and are lost on restart (recoverable via retry).
- Progress is committed from the worker session; many concurrent large downloads are untested.
- IMERG files are global; AOI subsetting is a later step. IMERG is Final Run (~3.5 month latency), ~0.1 degree grid.
- Landslide Catalog is a 2016 export: incomplete, not current.
- Search returns at most `MAX_GRANULES_PER_REQUEST` granules; there is no pagination beyond that.
- Orchestrator passes the provider directory as `dest_dir`, so on-disk names are the provider's original filename; the `<YYYYMMDD>__` prefix is applied only by `storage.target_path` (used when `dest_dir` is not given). See [data-storage.md](data-storage.md).
- `UNAVAILABLE` status is never set.
- Granule files other than the primary data file (e.g. NISAR PNG browse images) are ignored.
- SMAP radar products have limited coverage (radar failed in 2015).
- Collections are verified against CMR on 2026-11-14; catalogs change.

## Verification status

| Capability | Implemented | Tested with mocks | Tested against live NASA services | Not yet verified |
|---|---|---|---|---|
| Collection discovery (NISAR, NASADEM, GPM, SMAP) | yes | yes | anonymous read-only CMR collection searches on 2026-11-14 | GPM half-hourly/monthly provider mapping (verified present in CMR only) |
| Granule search + AOI post-filter | yes | yes | a few anonymous granule searches | search at scale; all products/maturities |
| Registration in PostgreSQL | yes | yes (DB tests need PostGIS) | n/a | n/a |
| Earthdata login | yes | yes | **no, never performed** | live login via `.env` and `~/.netrc` |
| File download (resume, retry, atomic) | yes | yes | **no files downloaded** | live authenticated download; concurrent executor under load |
| File validation | yes | yes (synthetic files) | no | real NISAR HDF5 structure; real NASADEM/IMERG files |
| Landslide catalog import | yes | yes | no | GLC date day/month ordering (assumed MM/DD); first real import |
| REST API / CLI | yes | yes (FastAPI TestClient + CLI with fake services; 157 backend tests) | in Docker on 2026-11-14: `GET /data/collections?refresh=true` (11 real collections) and a dry-run `POST /data/search` returned real NISAR GUNW granules as `metadata_only`; DB stayed at 0 rows | `POST /downloads` against real files; `landslide-events/import` against the real CSV; CLI against live services |
