# Deployment runbook

Status (2026-11-15): the development stack was run many times; the **production profile has been validated with `docker compose config` only and has NOT been deployed**, and the CI workflow has not been run on a remote. Treat the steps below as a checked procedure, not a tested deployment. The platform is a research prototype, not an operational warning system.

## Prerequisites
Docker with Compose v2.24 or later (the production file uses `!reset`), 8 GB RAM free for the backend image build and processing, disk for `./data` (NISAR GUNW files are 1.2-2 GB each), a `.env` copied from `.env.example`.

## Configure
Set in `.env`: `POSTGRES_PASSWORD` (strong, unique), `SECRET_KEY`, `CORS_ORIGINS` (exact browser origin of the frontend), `NEXT_PUBLIC_API_URL` (URL the browser uses for the API; baked into the frontend at build time), optional `EARTHDATA_USERNAME`/`EARTHDATA_PASSWORD` (only for downloads). Never commit `.env`. Leave `PREDICTION_BACKEND` unset (`none`); `NEXT_PUBLIC_USE_MOCK_PREDICTIONS` stays unset (N/A views) unless you want the labelled mock layouts.

## Start
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose ps                         # all three healthy
curl -s http://localhost:8000/api/v1/health   # {"status":"ok",..., "database":"connected"}
```
The backend runs `alembic upgrade head` on start. The production file removes the database port, adds restart policies, memory limits, read-only root filesystems, dropped capabilities and `no-new-privileges`. UNVERIFIED: the read-only containers have not been run; if the backend needs another writable path, add a tmpfs or volume for it.

## Health and logs
`/api/v1/health` (liveness and database connectivity) is also the readiness probe used by Compose. Logs are JSON lines on stdout (`docker compose logs -f backend`); credentials are scrubbed from error messages, which is tested.

## Backup and restore
`scripts/backup.sh` writes `backups/<UTC timestamp>/{db.dump,data.tar.gz,SHA256SUMS}`. Verified 2026-11-15: a custom-format dump of a PostGIS database restores into a fresh database (schema restored; the throwaway database held no rows). Restore:
```bash
docker compose exec -T postgres psql -U precursor -d postgres -c "CREATE DATABASE precursor_restore"
docker compose exec -T postgres psql -U precursor -d precursor_restore -c "CREATE EXTENSION IF NOT EXISTS postgis"
docker compose exec -T postgres pg_restore -U precursor -d precursor_restore --no-owner < backups/<ts>/db.dump
tar -xzf backups/<ts>/data.tar.gz            # restores ./data
```
Check the restored database, then swap names or point `DATABASE_URL` at it. Schedule the script (cron) and copy `backups/` off the host; the volume holds downloaded NASA data.

## Upgrade and rollback
Back up first. `git pull` (or copy the release), rebuild, `up -d`. Migrations: `docker compose exec backend alembic current`; roll one step back with `alembic downgrade -1`. Downgrade to base and upgrade to head was verified on a throwaway database (5 steps each way, no drift).

## Tests before a release
```bash
cd backend && python -m pytest -q          # needs TEST_DATABASE_URL = throwaway precursor_t_* database, Earthdata variables unset
cd backend && python -m alembic check
cd frontend && npx tsc --noEmit && npm test && npm run build
```
The CI workflow `.github/workflows/ci.yml` runs the same steps plus `pip-audit` and `npm audit` (not yet run remotely).

## Security checklist and known gaps
Done: secrets only in `.env` (ignored), `.env.example` holds placeholders (tested), containers run as non-root on minimal images (tested), CORS limited to configured origins (tested), error bodies carry no stack traces (tested), landslide-catalog `file_path` import confined to the data root (fixed in Phase 10), Earthdata credentials checked before downloads are queued (fixed in Phase 10), `pip-audit` and `npm audit` reported no known vulnerabilities (2026-11-15; `pip-audit --no-deps`, so transitive packages were not audited). **Open, decision needed:** no authentication or authorisation on any endpoint (write/processing endpoints are open to anyone who can reach the API) and no rate limiting. Do not expose the API to the public internet; place it behind a reverse proxy with authentication and rate limits, or add them in a follow-up.

## Enabling a model later
Not part of deployment. Follow [ML_INTEGRATION](../architecture/ML_INTEGRATION.md); it needs the separately authorized ML stage and the validation in [EARLY_WARNING_VALIDATION_PROTOCOL](../scientific/EARLY_WARNING_VALIDATION_PROTOCOL.md).
