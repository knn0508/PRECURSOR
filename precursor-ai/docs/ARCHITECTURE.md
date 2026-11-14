# PRECURSOR AI Architecture (Phase 1)

## Overview

```
Browser (Next.js, :3000) --HTTP/JSON--> FastAPI (:8000, /api/v1) --SQLAlchemy--> PostgreSQL + PostGIS
                                              |
                                              +-- (future) services call ai_engine/* modules
                                              +-- (future) reads/writes data/ and models/
```

## Backend layering (`backend/app`)

| Layer | Path | Rule |
|---|---|---|
| API | `api/v1/*` | HTTP only: parse request, call service, return schema. |
| Services | `services/` | Business logic. Convert between models and schemas (e.g. PostGIS <-> GeoJSON). |
| Repositories | `repositories/` | All DB access. `BaseRepository` gives get/list/count/add/delete. |
| Models | `models/` | SQLAlchemy 2 ORM. Geometry in EPSG:4326. |
| Schemas | `schemas/` | Pydantic request/response contracts. Mirrored in `frontend/types/api.ts`. |
| Core | `core/` | Settings (env), JSON logging, exception handlers (`{"error": {code, message}}`). |

Dependencies point inward: API -> services -> repositories -> models. `ai_engine` never imports FastAPI.

## Database (Phase 1)

- `monitored_areas`: id, name, description, country, region, `geometry` (PostGIS GEOMETRY, SRID 4326, GiST index), area_type, timestamps.
- `satellite_sources`: id, name (unique), provider, satellite_type, description, is_active, created_at.
- `satellite_acquisitions`: id, satellite_source_id (FK, RESTRICT), area_id (FK, CASCADE), acquisition_date, orbit_direction, polarization, product_type, file_path, `metadata` (JSONB), processing_status, created_at. Index on (area_id, acquisition_date).

No prediction or risk tables exist yet.

Migrations: Alembic (`backend/alembic`). `0001` enables the `postgis` extension. `alembic check` reports no drift.

## How future phases plug in

| Phase | Where it lives | Integration point |
|---|---|---|
| Data acquisition | `ai_engine/data_acquisition` | Creates `satellite_acquisitions` rows; files in `data/raw`. Triggered by a new service + endpoint (or script in `scripts/`). |
| Preprocessing / InSAR | `ai_engine/preprocessing`, `ai_engine/insar` | Updates `processing_status`; products in `data/processed`; new table(s) for derived measurements via a new Alembic migration. |
| Time series | `ai_engine/time_series` | Reads measurements, writes derived features. |
| Risk + uncertainty + XAI | `ai_engine/risk_assessment`, `uncertainty`, `explainability` | New `predictions` table (model version, input version, score, uncertainty). Exposed via new `/api/v1/...` routers and rendered in the Risk Map, Predictions, Analytics pages (Recharts is added when charts exist). |
| Long-running jobs | future | If processing exceeds request time, add a task queue; Phase 1 deliberately has none. |

## Data provenance rule

Every dataset or number shown in the UI must be labelled as measured, synthetic/demo, or predicted. Phase 1 shows no scientific values: risk cards display N/A.

## Frontend

Next.js App Router. `app/dashboard/*` pages share `DashboardShell` (sidebar + header). Data access: `lib/api-client.ts` (timeout, typed errors) -> `services/*` -> `hooks/use-api.ts` -> components. `NEXT_PUBLIC_API_URL` is baked in at build time. MapLibre runs client-only with an offline dark style (no tile server); its worker is copied to `public/vendor` by `scripts/copy-maplibre-worker.mjs`.

## Phase 2: data acquisition

Code: `backend/app/services/data_acquisition/`. Guide: [phase-2-data-acquisition.md](phase-2-data-acquisition.md).

```
providers (NISAR/NASADEM/GPM/SMAP via CMR) -> AcquisitionSearchService -> MetadataRegistrationService
        -> AcquisitionOrchestrator -> DownloadManager -> FileValidationService -> registration + manifest
```

- Providers translate NASA responses into provider-neutral `GranuleRecord`s (metadata only); `registry.build_providers` loads those enabled by `ENABLE_*`.
- Search is anonymous; only downloads use Earthdata credentials (`EarthdataAuthenticationService`).
- Orchestrator runs jobs in an in-process thread pool; statuses advance only on evidence (`DISCOVERED` -> ... -> `VALIDATED`, or `FAILED`).
- `VALIDATED` means file integrity checks passed, not scientific validation.
- Tables (migration `0002`): `data_collections`, `data_acquisitions` (unique provider+granule_id, PostGIS footprint), `download_jobs`, `landslide_events`. Phase 1 `satellite_acquisitions` is untouched.
- Files: `data/raw/{nisar/<product>,nasadem,gpm/imerg,smap,landslide_catalog}`, provenance JSON in `data/metadata/`; mounted at `/data` in Docker.
- API under `/api/v1/data/*`; CLI `python -m app.cli`.

