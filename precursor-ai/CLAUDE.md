# PRECURSOR AI: project instructions

Scientific geospatial platform for NASA Space Apps *Dancing with the SARs*: acquire SAR/environmental data, process InSAR deformation, and prepare the platform for landslide early prediction (no ML model yet). 10-phase roadmap in [docs/project/ROADMAP.md](docs/project/ROADMAP.md). **Do not rename, merge, reorder or remove phases without explicit user authorization.**

Current phase and verified state: [docs/project/PROJECT_STATUS.md](docs/project/PROJECT_STATUS.md) (single source of truth; this file never states progress).

## Stack (verified from repo)

- Backend `backend/`: Python 3.12 (Docker), FastAPI, Pydantic v2, SQLAlchemy 2, GeoAlchemy2, Alembic, earthaccess, asf_search, numpy, h5py, rasterio, shapely. InSAR code: `backend/app/services/insar/`, environmental code: `backend/app/services/environmental/` (not `ai_engine/`).
- DB: PostgreSQL 16 + PostGIS (SRID 4326). Host port **55432**.
- Frontend `frontend/`: Next.js 16 App Router, React 19, TypeScript, Tailwind v4, MapLibre, Three.js/R3F, GSAP, Lenis, vitest.
- Infra: Docker Compose. `ai_engine/*` = READMEs only (no code yet).

## Session start (do this first)

1. Read this file, then [PROJECT_STATUS.md](docs/project/PROJECT_STATUS.md), then [NEXT_STEPS.md](docs/project/NEXT_STEPS.md).
2. Read the relevant `docs/phases/PHASE_NN.md` and any architecture doc the task touches. Read others only if relevant.
3. Verify the previous report against code/tests before building on it. Do not trust completion claims blindly.
4. Work only on the requested phase. Never start the next phase on your own.

## Task completion

Update, in this order: PROJECT_STATUS, NEXT_STEPS, TASK_LOG, root CHANGELOG.md (meaningful changes only), phase doc, architecture doc if the real design changed, PROJECT_MEMORY only for durable knowledge. Record real test output, never expected output. Rules: [.claude/rules/documentation.md](.claude/rules/documentation.md). Workflow skill: `.claude/skills/precursor-workflow/`.

## Hard rules

- **ML policy (see [scientific-integrity.md](.claude/rules/scientific-integrity.md)):** all ML/DL stays a placeholder. No training, fine-tuning, real inference, fabricated risk scores/predictions, or rule-based stand-ins for future models. Interfaces/schemas/contracts only. Real ML needs a separate, explicitly authorized phase after the roadmap is reviewed. Allowed by [ADR-0008](docs/adr/ADR-0008-ml-slot-and-labelled-mock-frontend.md): the reserved ML slot (`services/prediction/`, `PREDICTION_BACKEND=none`) and clearly labelled MOCK prediction views in the frontend only (flag default off, never in backend/DB/API). `ModelInputSpec` (Phase 5) is the single model-input contract.
- **ML track exception ([ADR-0009](docs/adr/ADR-0009-ml-development-track.md), 2026-11-15):** ML development is permitted ONLY inside the ML track (`ml/`, `data/ml/`, `docs/ml/`; rules in [.claude/rules/ml.md](.claude/rules/ml.md)); every other directory and every roadmap phase remains ML-free.
- **Second ML area ([ADR-0011](docs/adr/ADR-0011-displacement-forecast-module.md), 2026-11-15):** `ai_engine/time_series/displacement_forecast/` (ported displacement-forecast models) + read-only serving of its precomputed bundle (`/displacement-forecast`, `data/displacement_forecast/`). The backend never runs it; outputs are labelled research / inferred / not a warning.
- Deterministic science (preprocessing, InSAR, DEM slope/aspect, displacement, statistics) is allowed in its own phase.
- Never fabricate NASA acquisitions, availability, measurements, test results or progress. Unverified = `UNKNOWN` / `NOT_VERIFIED`.
- A catalog hit is not a download; a download is not scientific validation (`VALIDATED` = file integrity only).
- **Nothing is downloaded and no Earthdata login is attempted without the user approving specific files (name, source, size).**
- Synthetic data is always labelled; passing synthetic tests is not real-data validation (`REAL_DATA_VALIDATION: NOT_PERFORMED` until a real file is processed). A deformation raster is not a risk map.
- Never print, log, commit or return credentials. `.env` is gitignored and holds real Earthdata credentials; do not read it aloud.
- Do not modify working Phase 1/2 code outside the task scope. No new dependencies without justification.

## Commands

```bash
docker compose up -d --build            # stack: frontend :3000, API :8000/docs, postgres :55432
# backend (venv at backend/.venv; Windows: .venv/Scripts/python)
cd backend && python -m alembic upgrade head && python -m alembic check   # must report no drift
cd backend && python -m pytest -q       # needs TEST_DATABASE_URL = THROWAWAY PostGIS db (tests truncate tables)
# frontend
cd frontend && npx tsc --noEmit && npm test && npm run lint && npm run build
python -m app.cli --help                # from backend/: Phase 2 CLI
```

Test DB guard: `conftest.py` refuses DB tests unless the database name starts with `precursor_t`. Never write `export DATABASE_URL=X TEST_DATABASE_URL="$DATABASE_URL"` on one line (it once pointed tests at the dev DB); build the URL in its own variable and print the DB name first.

Run backend tests with `EARTHDATA_USERNAME`/`EARTHDATA_PASSWORD` **unset**; live credentials in the environment make 3 CLI tests fail (see PROJECT_MEMORY).

## Where things are

Memory: [PROJECT_MEMORY](docs/project/PROJECT_MEMORY.md) · Tasks: [TASK_LOG](docs/project/TASK_LOG.md) · Changes: [CHANGELOG.md](CHANGELOG.md) · Architecture: [docs/architecture/](docs/architecture/SYSTEM_OVERVIEW.md) · Decisions: [docs/adr/](docs/adr/README.md) · Science: [docs/scientific/](docs/scientific/SCIENTIFIC_LIMITATIONS.md) · Dev: [docs/development/](docs/development/DEVELOPMENT_WORKFLOW.md) · Phase 2 guide: [docs/phase-2-data-acquisition.md](docs/phase-2-data-acquisition.md).

## Local gotchas

Use the Write tool for files with apostrophes (bash heredocs break). `PROJ_LIB` on this machine points at PostgreSQL's proj.db; `app/core/geo_env.py` fixes it and must be imported before geo libs.
