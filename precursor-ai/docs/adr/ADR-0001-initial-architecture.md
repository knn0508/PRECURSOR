# ADR-0001: Initial technology stack and layering

- Status: ACCEPTED
- Date: 2026-11 (Phase 1; reconstructed from the Phase 1 brief and [ARCHITECTURE.md](../ARCHITECTURE.md))

## Context
Need a platform for geospatial/SAR work with a web dashboard, spatial queries and room for later Python scientific code.

## Decision
FastAPI + Pydantic v2 + SQLAlchemy 2 + GeoAlchemy2 + Alembic on PostgreSQL 16/PostGIS (SRID 4326); Next.js App Router + TypeScript + Tailwind v4 + MapLibre; Docker Compose. Backend layering API -> services -> repositories -> models; `ai_engine` never imports FastAPI. Large files stay on disk, metadata and footprints in PostGIS. Schema changes only via Alembic.

## Alternatives considered
Alternatives were not recorded in the repo: UNKNOWN. (Notably there is no task queue by design; see ADR-0003.)

## Consequences
Typed contracts mirrored in `frontend/types`; migration discipline (`alembic check`); Docker needed for the default path; DB tests need PostGIS.

## Related
[SYSTEM_OVERVIEW](../architecture/SYSTEM_OVERVIEW.md), [DATABASE_SCHEMA](../architecture/DATABASE_SCHEMA.md)
