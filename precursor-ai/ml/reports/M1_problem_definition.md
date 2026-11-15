# M1 problem definition

Date: 2026-11-15. Design document only; nothing here has been run. Terminology: a cell with no recorded event is **background**, never "negative" (absence of a record is not proof of stability). Parameters marked `PROPOSED` are decisions for the user at the M1 gate.

## Common rules
- Spatial unit: a cell of a reference grid (Phase 4 `REFERENCE_GRID`, metric CRS). `PROPOSED` cell: 30 m (matches NASADEM 1 arc-sec); coarser (e.g. 250 m) if IMERG/SMAP-driven.
- Inventory bias (carried into every report): catalogs are incomplete and biased to reported, accessible, populated places (see [LABELLED_DATASET](../../docs/scientific/LABELLED_DATASET.md)). Metrics measure agreement with the **inventory**, not with true landslide occurrence.
- Splits for both tasks: spatial-block CV (whole blocks, gap buffer >= largest event location radius, nested for tuning) **and** a temporal hold-out where dates exist (train <= cut-off, test after). No random pixel splits. Reuse the Phase 5 block/gap/leakage logic read-only as a reference, not as the final implementation.

## Task A: susceptibility (static)
- Question: where are slopes prone to fail.
- Target: binary per cell: 1 = a located landslide event falls in the cell (or within its accuracy radius, rule fixed in M3) during the study window `PROPOSED: all labelled years in the window`; 0 = background.
- Features: static conditioning factors only (terrain, land cover, soil, lithology, distance to river/fault/road, climatology such as mean annual rainfall); an InSAR-derived velocity may be added only if dated before every label it is used with.
- Label construction: catalog point -> buffer by `location_accuracy` -> positive cells; events with unknown/unparseable accuracy excluded and counted; background drawn outside `max(2 x radius, min buffer)` with terrain-stratified sampling; ratio and strategy are choices, reported, and stress-tested in M8 (a random-vs-stratified-vs-slope-matched comparison). Class balance is set by sampling, so **calibrated probabilities are not claimed**; only ranking metrics plus prevalence-corrected calibration on a representative hold-out (prior-corrected), if at all.
- Label noise: positional error (km-scale for many catalog rows), missing events (false background), duplicate reports, event date = report date.
- Needs from data: label points with coordinates and accuracy; DEM; land cover; soil; lithology; region large enough for >= a few hundred distinct events (count NOT_VERIFIED, see feasibility).

## Task B: trigger / early warning (dynamic)
- Question: will a landslide occur in this cell (or this alert zone) within H days.
- Time step `PROPOSED`: 1 day (IMERG daily). Horizon `PROPOSED`: H = 1 day primary, also 3 and 7 days; lead times 0/1/3/7 days between the last feature date and the window start. Features use only data with date <= t (no future information).
- Spatial unit `PROPOSED`: coarse alert zone (IMERG ~0.1 deg ~ 10 km), because daily rainfall cannot resolve slopes and catalog positions are km-scale; per-cell prediction deferred to a hybrid with Task A susceptibility as a static feature.
- Target: 1 if >= 1 located event with a date in (t, t+H] falls in the unit; else 0 (background day). Event date is often the report date, so dates carry +-1-day (or worse) noise.
- Features: rainfall windows (1,3,7,14,30 d cumulative, antecedent), SMAP soil moisture, static factors/susceptibility, InSAR velocity/change where a REAL dated product exists before t.
- Needs from data: events with dates **inside the span of the dynamic data used**, and enough of them per zone. Prevalence is very low (events per zone-day), so background days must be subsampled or cost-weighted, and results reported at the true prevalence.

## Metrics (both tasks, on held-out data only)
PR-AUC (primary, reported with the prevalence baseline), recall at a fixed false-alarm rate (e.g. FAR 5%/1% of background units; Task B also alerts per month), Brier score and reliability curve / ECE for Task B (and A if prior-corrected), ROC-AUC secondary only. Report mean and spread over spatial folds, not a pooled point; confidence by block bootstrap.

## Baselines
1. Prior (constant prevalence): sets the PR-AUC floor.
2. Rainfall threshold (Task B): cumulative-rainfall-duration (E-D) curve fitted on the training period only (Task B only, inside `ml/`).
3. Logistic regression on a few factors (slope, rainfall; plus soil moisture for B).
4. Tabular boosting (RF/XGBoost/LightGBM) is a model, not a baseline; it must beat 1-3 on held-out data to be worth keeping.

## What each task needs from data (summary)
| | Labels | Dynamic data | Static data | Satellite SAR |
|---|---|---|---|---|
| A | located events, accuracy, any years | none required | DEM, land cover, soil, lithology, distances | optional auxiliary |
| B | **dated** events inside the dynamic-data span | rainfall (IMERG), SMAP, optional InSAR time series | same as A | optional; needs long REAL series |
