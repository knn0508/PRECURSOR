# Prediction design (Phase 7): heads, units, targets, validation protocol

Status: DESIGN ONLY. No model exists, nothing here is a result. Every number marked *proposed* is a design choice to be fixed in the validation protocol of the separately authorized ML stage ([ADR-0008](../adr/ADR-0008-ml-slot-and-labelled-mock-frontend.md)). The ML track under `ml/` ([ADR-0009](../adr/ADR-0009-ml-development-track.md)) may refine it; this document is not a track result.

## 1. Two heads

| | Susceptibility ("where") | Trigger / early warning ("when") |
|---|---|---|
| Question | How prone is this cell to landsliding, long term? | Given recent conditions, is a landslide in this cell likely within the horizon? |
| Inputs | static Phase 4/5 features (slope, aspect, relief, lithology, land cover, distance layers, texture) | static features plus dynamic ones (rainfall accumulation/intensity, SMAP soil moisture, InSAR velocity/coherence, change features) |
| Unit | one cell | one cell and one time step |
| Output | probability that the cell is in the positive class (below) | probability of a landslide in the cell within the horizon |
| Phase 5/6 inputs available today | yes (synthetic-verified only) | **no**: per-point dynamic features are Phase 6 (NOT_STARTED); the Phase 5 dataset reserves `dyn__*` columns, all NOT_AVAILABLE |

## 2. Analysis units
- **Cell:** the Phase 4 reference grid cell ([REFERENCE_GRID](REFERENCE_GRID.md)); default UTM from the AOI centroid at 30 m (*proposed* default, user-selectable). Predictions are never finer than the coarsest input that matters; SMAP (9 km), IMERG (0.1 degree) and InSAR resolutions are far coarser than a 30 m cell, so dynamic inputs are shared by many cells (scale mismatch caveat).
- **Time step (trigger head):** 1 day (*proposed*; matches IMERG daily). Half-hourly IMERG is optional and unverified.

## 3. Target definitions (*proposed*, to be fixed before any training)
- Susceptibility positive: a catalogued event whose location uncertainty (`location_accuracy`) is within one cell, or within *Y* m (*Y* = max(cell size, accuracy radius)). Background cells are **unlabelled**, not "no landslide" (Phase 5 never calls them negatives).
- Trigger positive: an event in the cell (same rule) on a day within `(t, t + X]`; *X* in {1, 3, 7} days (*proposed*; the stated lead time and horizon must travel with every output as `horizon_days`).

## 4. Label-quality caveats
Catalogs are incomplete and biased to populated, accessible, media-covered places and to large or fatal events (inventory bias). Absence of an event proves nothing. Dates and coordinates are often approximate (`location_accuracy` vocabulary NOT_VERIFIED). The NASA Global Landslide Catalog is a one-time export whose last event is 2017-09-28 ([M1 census](../../ml/reports/M1_census_and_download_list.md)), so it cannot validate a NISAR-era (2025-) trigger model. Single-storm clusters inflate event counts (many events, few independent dates).

## 5. Risk categories (interpretation only)
Categories (for example low / moderate / high) are meaningful only as bins of a **calibrated** probability, chosen after validation against an independent inventory, with the base rate and the false-alarm cost stated. **No threshold, class boundary or colour mapping exists in code**, and `RiskModelOutput.risk_class` is filled only by a registered model. An uncalibrated score is a "relative score", never a probability. A deformation raster is not a risk map; LOS displacement is not vertical motion.

## 6. Training-data requirements (for the future stage)
Real dated inventory; real Phase 4-6 feature layers on a verified grid (Phase 2-5 real-data validation done); labelled dataset with spatial-block splits and the Phase 5 leakage checker; documented provenance and checksums; feature schema major version pinned in the model's `input_spec`.

## 7. Validation protocol (required before any claim)
- Splits: **spatial-block cross-validation** (block >= the autocorrelation range, buffer between folds) **and a temporal hold-out** (train strictly before test; for the trigger head also hold out whole storms).
- Baselines every model must beat: **logistic regression** on the same features, and a **rainfall-only** model (accumulation/intensity thresholds fitted on training data only).
- Metrics for rare events: **PR-AUC**, **recall at a fixed false-alarm rate** (report the rate), **Brier score**, **calibration curve** (reliability diagram); ROC-AUC only as a secondary figure because it is optimistic under imbalance.
- Imbalance: stratified background sampling is already in Phase 5; use class weights or undersampling on training folds only; never resample before splitting; report the base rate and expected prevalence shift between inventory and reality.
- Early-warning evaluation (Phase 10): hit rate, false-alarm rate, lead time on temporal hold-out; `NOT_APPLICABLE` until a real model exists.
- Inventory-bias caveat is reported with every metric: scores measure agreement with a biased catalog, not with all landslides.

## 8. Future ML gate
A later, separately authorized stage requires: a real dated inventory, real Phase 4-6 feature layers, an approved validation protocol (this section, refined), and an approved model family and compute budget. Until then `PREDICTION_BACKEND=none` and every endpoint answers `MODEL_NOT_TRAINED`.
