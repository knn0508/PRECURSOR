# PRECURSOR AI

AI-powered early landslide risk platform built for NASA Space Apps Challenge, *Dancing with the SARs*. It will analyze SAR observations (Sentinel-1, NISAR), detect surface deformation with InSAR, study temporal change, and estimate future landslide risk.

> **Status: Phase 1 complete; Phase 2 (data acquisition) implemented but live acquisition NOT verified.** There is no SAR processing, no model and no risk calculation yet. The dashboard shows N/A for risk figures on purpose. Nothing here is a validated prediction. Current state: [docs/project/PROJECT_STATUS.md](docs/project/PROJECT_STATUS.md).

## Landing page

`/` is a scroll-driven 3D story (Three.js, React Three Fiber, GSAP ScrollTrigger, Lenis) that links to the dashboard at `/dashboard`. All visuals are illustrative, not real measurements. See [docs/CINEMATIC.md](docs/CINEMATIC.md).

## Architecture

```
Next.js (3000) --> FastAPI /api/v1 (8000) --> PostgreSQL + PostGIS
                         |
                         +-- future: ai_engine/* (acquisition, InSAR, time series, risk, uncertainty, XAI)
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Stack

Frontend: Next.js (App Router), TypeScript, Tailwind CSS v4, shadcn-style components (Radix Slot + cva), MapLibre GL JS, Lucide, Three.js + React Three Fiber + drei, GSAP + ScrollTrigger, Lenis. Backend: Python 3.11+, FastAPI, Pydantic, SQLAlchemy 2, GeoAlchemy2, Alembic. DB: PostgreSQL 16 + PostGIS 3.4. Infra: Docker Compose. Recharts is not installed yet; it arrives with the first real chart.

## Repository structure

```
frontend/   Next.js app (app/, components/, hooks/, lib/, services/, types/)
backend/    FastAPI app (app/{api,core,database,models,repositories,schemas,services}, alembic/, tests/)
ai_engine/  Future scientific modules (READMEs only in Phase 1)
data/       raw/ processed/ external/ samples/  (contents gitignored)
models/     checkpoints/ evaluation/
docs/  notebooks/  scripts/  tests/
```

## Prerequisites

Docker Desktop (for the compose path), or Python 3.11+, Node 20+ and a PostGIS database for local development.

## Environment

```bash
cp .env.example .env     # then edit POSTGRES_PASSWORD, SECRET_KEY
```

See `.env.example` for every variable. Never commit `.env`. The DB is published on host port **55432** by default (5432/5433 are commonly taken by a local Postgres); change `POSTGRES_HOST_PORT` and `DATABASE_URL` together if needed.

## Run with Docker Compose

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- API docs (Swagger): http://localhost:8000/docs
- Backend applies Alembic migrations on start; Postgres data persists in the `postgres_data` volume.

## Run locally (no Docker for the apps)

```bash
docker compose up -d postgres            # PostGIS only

# backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://precursor:<password>@localhost:55432/precursor
alembic upgrade head
uvicorn app.main:app --reload

# frontend (new terminal)
cd frontend
npm install
npm run dev
```

## API (`/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | status, app name, version, DB connectivity (`degraded` if DB down) |
| GET | `/system/info` | name, version, environment, module registry (available vs planned) |
| GET | `/areas` | list monitored areas (`offset`, `limit`) |
| GET | `/areas/{id}` | one area (GeoJSON geometry) |
| POST | `/areas` | create an area (GeoJSON Polygon/MultiPolygon, EPSG:4326) |
| GET | `/acquisitions?limit=` | latest satellite acquisition metadata |

Errors use `{"error": {"code", "message", "details?"}}`.

## Testing

```bash
# backend: needs PostGIS (see above). DB tests are SKIPPED, not passed, if it is unreachable.
cd backend && DATABASE_URL=... pytest

# frontend
cd frontend && npm run lint && npm test && npm run build
```

Note: backend tests truncate the tables of the database they run against. Use a throwaway database via `TEST_DATABASE_URL`; the test suite refuses any database whose name does not start with `precursor_t` ([details](docs/development/TESTING_STRATEGY.md)).

## Phase 2: data acquisition

Finds, downloads, checks and registers NASA source data (NISAR, NASADEM, GPM IMERG, optional SMAP, Global Landslide Catalog) for a user-supplied AOI. It does no SAR processing, modelling or risk scoring. Full guide: [docs/phase-2-data-acquisition.md](docs/phase-2-data-acquisition.md).

```bash
cd backend && alembic upgrade head
# put your AOI in data/aoi/ (none ships), then (flags: see --help):
python -m app.cli collections                      # discover collections (no login)
python -m app.cli discover --dry-run --help        # search an AOI without writing to the DB
# downloads need EARTHDATA_USERNAME / EARTHDATA_PASSWORD in .env (or ~/.netrc)
```

> **Honesty note:** during development only anonymous catalog searches were run against live NASA services. No NASA data file has been downloaded and no Earthdata login has been performed; the download path is tested with mocks only. The Landslide Catalog is a 2016 export and is not a complete or current inventory.

## Phase 4: environmental integration

Per-area environmental layers and descriptive features (terrain, rainfall, SMAP soil moisture, soil, land cover, cataloged landslides, earthquakes, Phase 3 references, plus user-provided lithology, NDVI and river/fault/road distances) aligned to one common reference grid and described by a stack manifest, with provenance and quality reports: API `/api/v1/environmental/*`, page `/dashboard/environmental`. Verified on **synthetic data only**; no real dataset has been processed and nothing is a risk score or prediction. User-provided layers are placed in `data/external/` (nothing is downloaded). Details: [docs/phases/PHASE_04.md](docs/phases/PHASE_04.md), [reference grid](docs/scientific/REFERENCE_GRID.md), [SMAP](docs/scientific/SMAP_METHODOLOGY.md), [external layers](docs/scientific/EXTERNAL_LAYERS.md).

## Project documentation

Instructions for Claude Code: [CLAUDE.md](CLAUDE.md). Status, roadmap, next steps, memory and task log: [docs/project/](docs/project/PROJECT_STATUS.md). Architecture: [docs/architecture/](docs/architecture/SYSTEM_OVERVIEW.md). Decisions: [docs/adr/](docs/adr/README.md). Changes: [CHANGELOG.md](CHANGELOG.md).

## Scientific integrity

Real measurements, synthetic demo data and model predictions must always be labelled as such. Risk scores will not be presented as probabilities without calibration and validation. InSAR phase-based displacement is not the same as image change detection. See `ai_engine/*/README.md`.
