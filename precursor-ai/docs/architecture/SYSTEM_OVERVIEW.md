# System overview

Describes the **implemented** system as of 2026-11-14. Layering, Phase 1 design and future integration points: [../ARCHITECTURE.md](../ARCHITECTURE.md) (kept as the base architecture document; this file indexes the architecture set).

```
Browser (Next.js :3000) --HTTP/JSON--> FastAPI (:8000 /api/v1) --SQLAlchemy--> PostgreSQL+PostGIS (:55432 on host)
                                           |
                                           +--> services/data_acquisition --> NASA CMR / Earthdata (anonymous search; authed download)
                                           +--> ./data volume (/data in Docker): raw files + provenance manifests
```

## Components

| Component | Location | Status |
|---|---|---|
| API (areas, acquisitions, health, system, data/*) | `backend/app/api/v1/` | implemented |
| Services / pipeline | `backend/app/services/`, `.../data_acquisition/` | implemented (live downloads NOT_VERIFIED) |
| Repositories | `backend/app/repositories/` | Phase 1 entities only |
| Models + migrations | `backend/app/models/`, `backend/alembic/versions/` | `0001`-`0005` |
| CLI | `backend/app/cli/` | implemented |
| Dashboard + landing | `frontend/app`, `frontend/components` | implemented; shell for risk pages |
| InSAR processing | `backend/app/services/insar/`, `api/v1/insar.py` | implemented (Phase 3), synthetic-tested; real-data validation NOT_PERFORMED |
| Environmental integration (16-stage pipeline, reference grid, stack manifest) | `backend/app/services/environmental/`, `api/v1/environmental.py` | implemented (Phase 4), synthetic-tested; real-data validation NOT_PERFORMED ([PHASE_04](../phases/PHASE_04.md)) |
| Feature extraction + labelled sample dataset | `backend/app/services/features_cv/`, `api/v1/features_cv.py` | implemented (Phase 5), synthetic-tested; real-data validation NOT_PERFORMED; files + manifest only (no DB table); no ML ([ADR-0007](../adr/ADR-0007-feature-extraction-and-labelled-dataset.md)) |
| `ai_engine/*` | READMEs only | not implemented (`ai_engine/insar` points to the backend module) |
| `models/` | `.gitkeep` only | no ML models (policy) |

## Frontend/backend communication
Browser calls `NEXT_PUBLIC_API_URL` (build-time, default `http://localhost:8000/api/v1`) through `frontend/lib/api-client.ts` -> `services/*` -> `hooks/use-api.ts`. CORS from `CORS_ORIGINS`. Errors use `{"error": {code, message, details?}}`.

## External providers
NASA CMR via `earthaccess` (anonymous search), ASF via `asf_search` (fallback search), Earthdata Login (downloads only), NASA Open Data Portal CSV (landslide catalog). See [../nasa-data-sources.md](../nasa-data-sources.md).

## Related
[PROJECT_STRUCTURE](PROJECT_STRUCTURE.md) · [DATABASE_SCHEMA](DATABASE_SCHEMA.md) · [API_DOCUMENTATION](API_DOCUMENTATION.md) · [DATA_PIPELINE](DATA_PIPELINE.md) · [COMPONENT_DEPENDENCIES](COMPONENT_DEPENDENCIES.md)
