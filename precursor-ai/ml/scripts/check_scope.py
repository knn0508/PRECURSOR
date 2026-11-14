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
    return rel.startswith(ALLOWED_GOVERNANCE)


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
