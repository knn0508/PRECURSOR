# ML experiment log and tracking convention

No experiments have been run. Plain files, no tracking server (MLflow is optional, see [ML_ENVIRONMENT](ML_ENVIRONMENT.md)).

## Convention

Every run writes `ml/runs/<run_id>/` (gitignored) containing:

| File | Content |
|---|---|
| `config.yaml` | the full resolved config used |
| `meta.json` | `run_id`, `config_hash`, `seed`, `dataset_hash`, `code_version`, `started_utc`, `command`, package versions |
| `metrics.json` | held-out metrics only, each tagged with its split (`spatial_block_cv`, `temporal_holdout`) |
| `artifacts/` | models, plots, predictions, SHAP outputs |

- `run_id` = `<stage>-<UTC yyyymmddThhmmss>-<config_hash[:8]>`.
- `config_hash` = SHA-256 of the canonical JSON (sorted keys) of the resolved config.
- `seed` = explicit integer in the config; every RNG is seeded from it.
- `dataset_hash` = SHA-256 over the sorted (path, SHA-256) list of input files, matching [DATASET_LOG](DATASET_LOG.md) rows.
- `code_version` = git commit if the repo has one, otherwise the SHA-256 of `ml/src/` files plus the string `no-git`. (The repo has no git commits yet.)
- A metric on training data or a tuned fold is never written to `metrics.json` as performance; label it `train` or `inner_cv` and keep it out of reports.
- A run on synthetic data sets `"synthetic": true` in `meta.json` and writes no `metrics.json` results section a report may cite.

## Log

| Run id | Stage | Dataset hash | Split | Headline held-out metric | Notes |
|---|---|---|---|---|---|
| | | | | | |
