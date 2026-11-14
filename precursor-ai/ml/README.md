# ML track (ADR-0009)

Separate landslide early-prediction ML work, stages M0-M9 ([Prompts.md](../Prompts.md), last section). Isolated from the 10 roadmap phases: nothing here is wired into the backend, frontend, API or DB, and `PREDICTION_BACKEND` stays `none`.

Status: [docs/ml/ML_STATUS.md](../docs/ml/ML_STATUS.md). Rules: [.claude/rules/ml.md](../.claude/rules/ml.md).

| Path | Purpose |
|---|---|
| `src/precursor_ml/` | package (stub in M0; no model code) |
| `configs/` | run configs (YAML), hashed into every run |
| `notebooks/` | exploration; never the source of a reported metric |
| `reports/` | one `M<n>_*.md` per stage |
| `scripts/` | `check_scope.py` scope guard |
| `tests/` | pytest (`pytest.ini` here) |
| `../data/ml/` | `raw/ interim/ processed/ splits/` (gitignored) |

Run the tests and the guard from `precursor-ai/` (no ML packages are needed for M0):

```bash
backend/.venv/Scripts/python -m pytest ml/tests -q -c ml/pytest.ini
backend/.venv/Scripts/python ml/scripts/check_scope.py check
```

The ML environment is separate from the backend image; the dependency list awaits approval ([ML_ENVIRONMENT](../docs/ml/ML_ENVIRONMENT.md)). No `ml/requirements.txt` exists until then.
