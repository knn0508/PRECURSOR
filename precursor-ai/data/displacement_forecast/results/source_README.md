# PRECURSOR AI — NISAR-aware landslide LOS-motion forecasting (NASA Space Apps 2026)

Research demonstrator. **Not an operational warning system. The model outputs no landslide probability.**

- **Training data:** OPERA DISP-S1 (Sentinel-1 C-band LOS displacement, 2016→2026), Portuguese Bend, California.
- **Observation layer:** NISAR L-band GUNW (provisional) and GCOV (validated). These are shown to the user and are **never** used as model input.
- **Models:** Nava 2023 (MLP/LSTM/GRU), Li 2025 (TCN, LSTM-TCN), Strnad 2026 (multi-task onset head), plus non-DL baselines. See `docs/literature_review.md` and `docs/experiments.md`.

## Run
```powershell
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
# Earthdata credentials (needed for OPERA / NISAR / IMERG downloads):
#   C:\Users\<you>\_netrc  ->  machine urs.earthdata.nasa.gov login <user> password <pass>
$env:PYTHONPATH="src"; .venv\Scripts\python -m pytest -q tests        # leakage / causality / unit tests
.venv\Scripts\python scripts\make_notebook.py                         # regenerate notebook from code
.venv\Scripts\jupyter lab notebooks\01_precursor_pipeline.ipynb       # or run headless with nbconvert --execute
```

The outputs below are written only after a real run:
- `data/manifest.csv`
- `results/*.csv`
- `artifacts/{metrics.json, forecast.tif, provenance.json, model.pt}`

## Reuse the trained model without downloads or Earthdata login
Everything needed to rerun the saved B0 model (E3 LSTM-TCN) on the real data is in the repo:

| file | content |
|---|---|
| `data/processed/opera_F16940_stack.nc` | processed OPERA DISP-S1 F16940 stack (2016-10 → 2026-03, 30 m, 150×187, common-mode + elevation-tropo removed): `cum_mm`, `valid`, `coherence` |
| `data/processed/imerg_daily_aoi.csv` | GPM IMERG daily rain at the AOI (built into the samples; E3 itself does not use rain features) |
| `artifacts/model.pt` | network weights only (`state_dict`) |
| `artifacts/scaler.npz` | train-only mean/std scaler (`xm, xs, sm, sd, ym, ys`), `feat_names`, `feat_idx` used by E3 |

The DEM (Copernicus GLO-30) is read from a public bucket; no login is needed.
`scripts/export_scaler.py` rebuilds the scaler, reloads `model.pt`, issues the forecast for the last acquisition
(2026-03-11, +12 d), and checks it against `artifacts/forecast.tif`. Result in `artifacts/scaler_verification.json`:
20 184 pixels, identical NaN pattern, max difference 0.0 mm.
```powershell
$env:PYTHONPATH="src"; .venv\Scripts\python scripts\export_scaler.py
```
Note that the data ends on 2026-03-17. A forecast for a later date requires new OPERA granules.

## Layout
`src/precursor/`:
- `discovery.py`: CMR search
- `opera.py`: remote AOI subsetting and reference chaining
- `nisar.py`
- `ancillary.py`: DEM and IMERG
- `dataset.py`: causal samples, splits, onset labels
- `models.py`
- `train.py`

## Citations
- Nava et al. 2023, doi:10.1007/s10346-023-02104-9
- Li et al. 2025, doi:10.1007/s11069-024-06937-y
- Strnad et al. 2026, doi:10.1038/s41598-025-29084-1
- Data: NASA/JPL OPERA, NASA/ISRO NISAR via ASF DAAC, NASA GPM IMERG (GES DISC), Copernicus GLO-30 DEM.
