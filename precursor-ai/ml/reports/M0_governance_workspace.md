# M0 report: governance and workspace

Date: 2026-11-15. Status: IN_PROGRESS (awaiting dependency approval).

## Done
ADR-0009 + index + pointers; exception paragraphs in CLAUDE.md and scientific-integrity.md; `.claude/rules/ml.md`; `ml/` skeleton; `data/ml/*` READMEs and gitignore; `docs/ml/*`; tracking convention ([EXPERIMENT_LOG](../../docs/ml/EXPERIMENT_LOG.md)); scope guard `ml/scripts/check_scope.py`.

## Real results
- `pytest ml/tests -c ml/pytest.ini`: 3 passed (backend venv Python 3.13.9).
- `check_scope.py check`: scope ok (baseline of 497 files taken before edits; only allowlisted governance files differ).
- Environment measured: see [ML_ENVIRONMENT](../../docs/ml/ML_ENVIRONMENT.md); GPU RTX 4060 Laptop 8 GB.

## Not verified
CUDA/PyTorch GPU usability; wheel availability of proposed packages on Python 3.13; backend tests not re-run (backend untouched, guard confirms).

## Risks
No git history, so the guard relies on a local size+mtime snapshot. Backend venv is Python 3.13 vs 3.12 in Docker.

## Decision needed
Approve, edit or strike the dependency list, plus the four choices at the end of ML_ENVIRONMENT.md (PyTorch deferral, tracking, venv location, installer).
