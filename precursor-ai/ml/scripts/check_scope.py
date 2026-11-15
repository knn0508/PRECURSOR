"""Scope guard for the ML track (ADR-0009).

`snapshot` records (size, mtime_ns) of every repo file outside the ML-owned paths.
`check` fails if any such file was added, removed or changed since the snapshot,
except the governance files the M-prompts explicitly allow (ALLOWED_GOVERNANCE).

Usage (from precursor-ai/):
    python ml/scripts/check_scope.py snapshot
    python ml/scripts/check_scope.py check

Limits: there is no git history here, so the baseline is a local snapshot file
(data/ml/.scope_baseline.json, gitignored). size+mtime can miss an edit that keeps both
(rare); it is a guard against accidents, not a security control.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "data" / "ml" / ".scope_baseline.json"

# The ML track may write here freely.
ML_OWNED = ("ml/", "data/ml/", "docs/ml/")
# Governance files the M-prompts tell the track to update (docs, rules, ADRs, index files).
ALLOWED_GOVERNANCE = (
    "CLAUDE.md",
    "CHANGELOG.md",
    ".gitignore",
    ".claude/rules/",
    "docs/adr/",
    "docs/project/",
)
# ADR-0011 (2026-11-15): the displacement-forecast module and its read-only wiring were authorised by the user; not susceptibility-track work.
ADR_0011_PATHS = (
    "ai_engine/time_series/",
    "data/displacement_forecast/",
    "backend/app/api/v1/displacement_forecast.py",
    "backend/app/services/displacement_forecast/",
    "backend/tests/displacement_forecast/",
    "backend/app/services/data_acquisition/providers/opera.py",
    "backend/tests/data_acquisition/test_opera_provider.py",
    "frontend/components/displacement/",
    "frontend/components/pages/",
    "frontend/app/dashboard/displacement/",
    "frontend/services/displacement.ts",
    "frontend/types/displacement.ts",
    "frontend/lib/displacement-helpers.ts",
    "frontend/tests/displacement-helpers.test.ts",
    ".venv-displacement/",
    # edited (not new) files, ADR-0011 wiring: router/system registry, OPERA provider enum/storage/registry/config/schema, nav, data types
    "backend/app/api/v1/router.py", "backend/app/api/v1/system.py", "backend/app/core/config.py", "backend/app/schemas/data_acquisition.py",
    "backend/app/services/data_acquisition/types.py", "backend/app/services/data_acquisition/storage.py",
    "backend/app/services/data_acquisition/registry.py", "docker-compose.yml", ".env.example",
    "frontend/lib/navigation.ts", "frontend/types/data.ts", "frontend/components/data/data-overview.tsx",
    "frontend/app/dashboard/alerts/", "frontend/app/dashboard/analytics/", "frontend/app/dashboard/settings/",
    "frontend/app/dashboard/satellite-data/", "frontend/components/dashboard/placeholder-page.tsx",
)
# Heavy or generated trees that are not part of the comparison.
SKIP_DIRS = {".venv", "node_modules", ".next", "__pycache__", ".pytest_cache", ".git"}


def _scan() -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for p in ROOT.rglob("*"):
        if not p.is_file() or SKIP_DIRS & set(p.relative_to(ROOT).parts):
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(ML_OWNED):
            continue
        st = p.stat()
        out[rel] = [st.st_size, st.st_mtime_ns]
    return out


def _allowed(rel: str) -> bool:
    return rel.startswith(ALLOWED_GOVERNANCE + ADR_0011_PATHS)


def violations(baseline: dict[str, list[int]], current: dict[str, list[int]]) -> list[str]:
    changed = [f"changed: {k}" for k in baseline.keys() & current.keys() if baseline[k] != current[k]]
    added = [f"added: {k}" for k in current.keys() - baseline.keys()]
    removed = [f"removed: {k}" for k in baseline.keys() - current.keys()]
    return sorted(v for v in changed + added + removed if not _allowed(v.split(": ", 1)[1]))


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in {"snapshot", "check"}:
        print(__doc__)
        return 2
    if argv[1] == "snapshot":
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        data = _scan()
        BASELINE.write_text(json.dumps(data, sort_keys=True))
        print(f"snapshot: {len(data)} files outside ML-owned paths")
        return 0
    if not BASELINE.exists():
        print("no baseline; run `snapshot` first")
        return 2
    bad = violations(json.loads(BASELINE.read_text()), _scan())
    for v in bad:
        print("OUT OF SCOPE", v)
    print("scope ok" if not bad else f"{len(bad)} out-of-scope change(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
