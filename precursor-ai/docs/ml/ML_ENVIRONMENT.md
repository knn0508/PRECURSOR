# ML environment (APPROVED and installed 2026-11-15)

Status: APPROVED by the user 2026-11-15 and installed in `ml/.venv` (Python 3.13.9, uv). Separate from the backend image and `backend/.venv`. Pins: [requirements.txt](../../ml/requirements.txt) (direct) and [requirements.lock.txt](../../ml/requirements.lock.txt) (all). The original proposal table is kept below.

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
| pytest | tests | now |

## Decisions (user, 2026-11-15)

1. Package list approved. 2. PyTorch deferred to M7 (not installed); when installed it must be the CUDA build and GPU use verified. 3. Tracking: plain files. 4. Environment: `ml/.venv`. The user has CUDA and asked that any GPU-capable library use its CUDA build, verified.

## GPU verification (measured 2026-11-15)

Driver: NVIDIA 621.14, CUDA UMD 13.5; toolkit `nvcc` 13.2.78; GPU RTX 4060 Laptop, 8188 MiB.

| Library | Version | GPU result |
|---|---|---|
| xgboost | 3.4.1 | **CUDA build** (`USE_CUDA=True`); `device="cuda"` trained 2M x 40, 300 trees depth 8 in 5.6 s with peak GPU utilisation 88% (sampled with nvidia-smi) |
| lightgbm | **4.6.0, local CUDA build** (user asked for CUDA, 2026-11-15) | `device_type="cuda"` trains on the GPU: 2M x 40, 200 trees, 6.1 s vs 11.5 s CPU, peak GPU util 78%. The PyPI wheel (4.7.0) is CPU only and 4.7.0's CUDA build needs NCCL (no Windows build), so 4.6.0 was built with MSVC + CUDA 13.2 for sm_89 with a 4-file compatibility patch. Unofficial; recipe and caveats in [ml/build/lightgbm_cuda_win](../../ml/build/lightgbm_cuda_win/README.md) |
| scikit-learn, shap, optuna, geopandas | 1.9.1, 0.54.1, 5.0.0, 1.2.0 | CPU libraries (shap TreeExplainer GPU path via xgboost not tested) |
| torch | not installed | deferred to M7; install the CUDA wheel then and verify `torch.cuda.is_available()` |

Imports of all packages verified; `ml/tests` 3 passed in this venv.

Caveat: GPU histogram training is not bit-identical to CPU or across devices. Log the device in `meta.json` and do not compare a GPU run to a CPU run as if the seed alone fixed the result. Reinstalling from `requirements.txt` replaces the CUDA build with the CPU wheel; rerun `ml/build/lightgbm_cuda_win/build.bat`.
