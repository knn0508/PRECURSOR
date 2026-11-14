# ML environment: dependency proposal (NOT INSTALLED, awaiting approval)

Status: PROPOSED. Nothing below was installed. The ML environment is separate from the backend image and `backend/.venv`; it gets its own `ml/requirements.txt` (pinned) only after approval. Pins are chosen and verified at install time, not now.

## What exists today (measured 2026-11-15)

- `backend/.venv`: Python **3.13.9** (the Docker backend image uses 3.12). Installed relevant packages: numpy 2.5.4, pandas 3.1.1, scipy 1.18.1, scikit-image 0.26.0, pyarrow 26.0.1, rasterio 1.5.2, shapely 2.2.0, pyproj 3.8.0, xarray 2026.9.0, pytest 9.2.0.
- Not installed there: scikit-learn, xgboost, lightgbm, shap, matplotlib, seaborn, geopandas, optuna, torch, mlflow.
- GPU: **NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB, driver 621.14** (from `nvidia-smi`; CUDA toolkit and PyTorch CUDA support not checked).

## Proposed packages

| Package | Why | When needed |
|---|---|---|
| numpy, pandas, scipy, pyarrow | arrays, tables, stats, Parquet I/O | M1+ (already in backend venv) |
| scikit-learn | RF/LR baselines, metrics, preprocessing, group/spatial CV utilities | M5-M7 |
| xgboost, lightgbm | gradient boosting (strong tabular models per literature table) | M7 |
| shap | explainability of tree models | M7-M8 |
| matplotlib, seaborn | EDA and report figures | M5 |
| geopandas | vector joins, spatial blocks, buffers (needs approval: pulls pyogrio/fiona) | M1-M4 |
| rasterio, shapely, pyproj | raster/vector I/O (already installed) | M2+ |
| optuna | hyperparameter search inside the inner CV only | M7 |
| pyyaml | read configs | M1+ |
| pytest | tests (installed) | now |

## Decisions needed

1. Approve this list (or strike items). Proposed to install only what each stage needs, starting with scikit-learn, matplotlib, geopandas, pyyaml at M1/M5.
2. **PyTorch: not proposed now.** Only if M7 shows a deep model is justified (8 GB VRAM would limit patch-CNN batch sizes; deep models underperformed RF in some literature).
3. **Experiment tracking:** plain files per [EXPERIMENT_LOG](EXPERIMENT_LOG.md) (recommended: no new dependency) vs MLflow (extra dependency and server/state).
4. **Environment:** new venv `ml/.venv` (recommended; Python 3.13 matches the current dev machine but differs from the backend image's 3.12, so a package missing 3.13 wheels is a risk to check at install) vs reuse `backend/.venv` (rejected: mixes ML into backend deps).
5. Optional `ml/requirements.txt` and a Windows install with `uv` or `pip`: your preference.
