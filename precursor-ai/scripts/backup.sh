#!/usr/bin/env bash
# Back up the PostGIS database (custom-format dump) and the data volume (./data) to ./backups/<timestamp>/.
# Usage: scripts/backup.sh            (run from the repository root with the stack up)
# Restore: see docs/development/DEPLOYMENT_RUNBOOK.md ("Restore"). Never commit ./backups (it can hold downloaded NASA files).
set -euo pipefail

DB="${POSTGRES_DB:-precursor}"
USER_="${POSTGRES_USER:-precursor}"
CONTAINER="${POSTGRES_CONTAINER:-$(docker compose ps -q postgres)}"
OUT="backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"

docker exec "$CONTAINER" pg_dump -U "$USER_" -d "$DB" -Fc > "$OUT/db.dump"
[ -s "$OUT/db.dump" ] || { echo "empty database dump" >&2; exit 1; }
tar -czf "$OUT/data.tar.gz" data
sha256sum "$OUT"/* > "$OUT/SHA256SUMS"
echo "backup written to $OUT"
