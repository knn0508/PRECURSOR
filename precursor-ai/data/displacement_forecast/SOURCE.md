# Displacement-forecast result bundle (third-party, NOT produced by this project)

Source: https://github.com/Farid145678/NASA_SPACE_APPS, commit 86c9d5c (pulled 2026-11-15; adds the processed OPERA stack, scaler and export_scaler.py), cloned 2026-11-15.
Files are copied unmodified from `artifacts/` and `results*/` of that repo. We did not re-run training or download OPERA/NISAR;
numbers are the repo author's own, not independently reproduced here. Research demonstrator. Not an operational warning.
Not a landslide probability.

Added in 86c9d5c: `processed/opera_F16940_stack.nc` (70 MB, processed OPERA DISP-S1 F16940 stack, 2016-10 to 2026-03), `processed/imerg_daily_aoi.csv`, `artifacts/scaler.npz`, `artifacts/scaler_verification.json` (author reports max diff 0.0 mm vs forecast.tif; not re-checked here yet).

Added by this project (2026-11-15, not from the source repo): `processed/static_terrain.npz` (Copernicus GLO-30 window, user-approved read), `artifacts/reproduction.json` (saved model reproduces the author's forecast.tif), `backtest/backtest.json` + `backtest/grids.npz` (forecast vs observed for issue dates 2025-12-29 to 2026-02-27, targets 2026-01-10 to 2026-03-11; made with the author's saved weights, nothing retrained, exploratory, see `held_out_note`). No OPERA F16940 granule newer than 2026-03-11 exists in the catalog (searched 2026-11-15), so nothing was downloaded.
