# time_series

Two things live here.

1. **Deterministic Phase 6 code** is in `backend/app/services/timeseries/` ([methodology](../../docs/scientific/TIME_SERIES_METHODOLOGY.md)).
2. **`displacement_forecast/`**: research displacement-forecast models ported from github.com/Farid145678/NASA_SPACE_APPS (commit 2a5f911), authorised by [ADR-0011](../../docs/adr/ADR-0011-displacement-forecast-module.md). Research, inferred, not a warning, not a landslide probability.

## displacement_forecast
12-day LOS displacement-increment forecasts (q10/q50/q90) from OPERA DISP-S1 stacks. Models: MLP, LSTM/GRU, TCN, LSTM-TCN, onset head (`models.py`); causal sample builder and splits (`dataset.py`); training and naive baselines (`train.py`); Kalman/OLS/Huber trend baselines (`kalman_trend.py`, `causal_velocity.py`, `trend_selection.py`, `trend_target_144d.py`); QA masks; OPERA/IMERG/DEM fetchers (`opera.py`, `discovery.py`, `ancillary.py`, `remote.py`; **never run without the user approving specific files**).

```bash
# own env OUTSIDE ai_engine/ (a repo test forbids weight-like files there), CUDA torch, not the backend image, not ml/.venv
uv venv --python 3.13 .venv-displacement            # from precursor-ai/
uv pip install --python .venv-displacement/Scripts/python.exe --index-url https://download.pytorch.org/whl/cu128 torch==2.11.0+cu128
uv pip install --python .venv-displacement/Scripts/python.exe -r ai_engine/time_series/requirements.txt
cd ai_engine/time_series && ../../.venv-displacement/Scripts/python -m pytest -q   # 58 pass, 2 skipped (reasons in -rs); synthetic arrays: mechanics only
../../.venv-displacement/Scripts/python -m displacement_forecast.pipeline --synthetic --out <dir>   # labelled synthetic smoke run on CUDA
```
Verified 2026-11-15: torch 2.11.0+cu128, `cuda.is_available()` True on the RTX 4060 Laptop GPU.

`pipeline.py` runs the whole chain on a stack (causal samples, chronological split, LSTM-TCN training, held-out metrics vs zero-motion/persistence/ridge, latest forecast with NaN = no estimate). Real stacks need OPERA files the user has approved by name; The author's saved model now runs without retraining: `python -m displacement_forecast.saved_model verify` (uses `artifacts/model.pt`, `scaler.npz`, `processed/opera_F16940_stack.nc`, `processed/static_terrain.npz`) reproduced his forecast.tif to 0.0016 mm. Data ends 2026-03-17; a later forecast needs new OPERA granules (user approval).

Served read-only at `/api/v1/displacement-forecast/*` and `/dashboard/displacement` from the result bundle in `data/displacement_forecast/` (see its `SOURCE.md`). The backend does not run the model.

Scientific constraints: chronological ordering and causal features only; forward splits, never random k-fold across time; compare with naive baselines (zero-motion, persistence, ridge) before claiming skill. The source reports a small gain over those baselines, a mostly masked landslide core in 2024-25, one site, and repeated test inspection.
