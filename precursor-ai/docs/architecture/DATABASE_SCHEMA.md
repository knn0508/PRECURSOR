# Database schema

PostgreSQL 16 + PostGIS, SRID 4326. Migrations: Alembic `0001` (Phase 1), `0002` (Phase 2), `0003`-`0005` (Phases 3-4). `alembic check` reported no drift on 2026-11-14. Column-level detail for Phase 2 tables: [../phase-2-data-acquisition.md](../phase-2-data-acquisition.md#database-schema) (canonical); source of truth is `backend/app/models/`.

| Table | Phase | Purpose | Key points |
|---|---|---|---|
| `monitored_areas` | 1 | User AOIs | `geometry` GEOMETRY 4326, GiST index |
| `satellite_sources` | 1 | Satellite/source registry | unique `name` |
| `satellite_acquisitions` | 1 | Phase 1 acquisition metadata | FK source (RESTRICT), FK area (CASCADE); not used by Phase 2 |
| `data_collections` | 2 | Verified NASA/ASF collections | provider, short name, version, maturity, discovered_at |
| `data_acquisitions` | 2 | Registered granules | unique (provider, granule_id); PostGIS footprint; maturity; status; `local_file_path`; checksum; JSONB `metadata_json` |
| `download_jobs` | 2 | Download job state | FK acquisition; status, progress, attempts, error_message |
| `insar_processing_runs` | 3 | One processing attempt per input + config | FK acquisition (SET NULL); status, stages/config/inspection/quality_report/warnings JSONB, `config_hash` (duplicate control), cancel flag; index (input_ref, config_hash) |
| `deformation_products` | 3 | Derived rasters (file on disk, relative to DATA_ROOT) | FK run (CASCADE), FK acquisition (SET NULL); units, CRS, dates, `data_origin`, `scientifically_validated` (always false so far), statistics JSONB, POLYGON 4326 footprint (GiST) |
| `environmental_processing_runs` | 4 | One pipeline run per monitored area | FK area (CASCADE); status, stages/config/quality_report/warnings JSONB, cancel flag; `reference_grid` JSONB (CRS, transform, size, resolution; migration `0005`) |
| `environmental_layers` | 4 | Processed or referenced layers (files on disk, relative paths) | FK area (CASCADE), FK run (SET NULL), FK deformation_product (SET NULL, InSAR references); layer_type, provider, dataset, version, `measurement_kind`, `data_origin`, `validation_status` (always NOT_VALIDATED), status, `input_hash`, CRS, native/processing resolution, temporal range, POLYGON 4326 footprint (GiST), provenance/quality/statistics JSONB; `temporal_kind` (static|dynamic, default static, set from the `TEMPORAL_OF` table) and `aligned_file_path` (aligned copy on the reference grid; the native file stays in `file_path`) (migration `0005`); `units` is 120 chars (migration `0004`) |
| `environmental_features` | 4 | Descriptive features per group per run | unique (run, group); values/units/lineage/warnings JSONB; origin and measurement kind |
| `earthquake_events` | 4 | USGS earthquakes as independent observations | unique (source, external_id); POINT 4326 (GiST); magnitude, depth_km, time |
| `landslide_events` | 2 | Global Landslide Catalog points | PostGIS point; `original_attributes` JSONB; dataset_version |

Relationships (verified in models): `data_acquisitions.collection_id -> data_collections` (RESTRICT); `data_acquisitions.monitored_area_id -> monitored_areas` (SET NULL); `download_jobs.acquisition_id -> data_acquisitions` (CASCADE). Unique constraints: `uq_collection_name_version` (short name + version), `uq_acq_provider_granule` (provider + granule_id), `uq_event_id_version` (external event id + dataset version). `landslide_events.geometry` is POINT 4326. Migration `0004` adds the four Phase 4 tables; `0005` adds the three columns named above. Migration `0003` adds the two Phase 3 tables (upgrade, downgrade, upgrade and `alembic check` verified 2026-11-14).

Acquisition status values: `DISCOVERED, QUEUED, DOWNLOADING, DOWNLOADED, VALIDATING, VALIDATED, FAILED, SKIPPED, UNAVAILABLE` (`UNAVAILABLE` is never set by code). `VALIDATED` = file integrity only.

No prediction, risk or time-series tables exist. Displacement exists only as registered raster files (`deformation_products`), not as per-pixel rows. Large files are never stored in the DB.

Live dev database state (2026-11-14): 0 collections, 0 areas, 0 acquisitions after a test-run incident truncated it (see [PROJECT_STATUS](../project/PROJECT_STATUS.md) issue 34); the collections are metadata and can be restored with the anonymous catalog refresh.
