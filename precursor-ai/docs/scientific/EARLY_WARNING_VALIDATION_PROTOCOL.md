# Early-warning validation protocol

**Status: protocol only. Every result is `NOT_APPLICABLE`: no model exists, so nothing has been measured and no number below is an expected value.** It extends [PREDICTION_DESIGN](PREDICTION_DESIGN.md) section 7 and applies to both heads of the ML slot ([ML_INTEGRATION](../architecture/ML_INTEGRATION.md)). A model may be enabled only after its model card reports these results on a real, dated inventory.

## Data and splits
- **Temporal hold-out:** train strictly before the cut date; test after it; buffer at least the horizon. For the trigger head also hold out whole storms/rainy seasons.
- **Spatial hold-out region:** at least one region never seen in training (different catchment or country), plus spatial-block cross-validation inside the training region (block size at least the autocorrelation range, buffer between folds).
- Both holds together for the headline figure; each also reported alone. Splits are written to a file with the dataset SHA-256 and checked with the Phase 5 leakage checker.

## Metrics (all with 95 % confidence intervals)
Hit rate (recall), false-alarm rate, precision, PR-AUC, Brier score, calibration curve and calibration error, recall at a fixed false-alarm rate (the rate is stated), ROC-AUC only as a secondary figure. Intervals by block bootstrap (resample spatial blocks and storms, not cells) so serial and spatial correlation do not make them too narrow.

## Early-warning specific
- **Lead time:** distribution of (event date - first alert date) for hits, per horizon; alerts issued after the event do not count; the alert rule (probability cut-off) is fixed on training data only.
- **Baselines every model must beat:** rainfall-threshold rule (intensity-duration or accumulation threshold fitted on training data only), rainfall-only model, logistic regression on the same features, and the climatological base rate. Report the difference with its interval, not only absolute scores.
- **Failure-case analysis:** list and map the false alarms and misses; characterise by terrain, land cover, season, rainfall regime, data gaps, coherence; check that suppression rules (outside valid region/time, low coverage, synthetic inputs) behave.
- **Performance under inventory bias:** evaluate on subsets with different reporting density (near roads/settlements vs remote) and event size; compare to a model of reporting probability if available; state that scores measure agreement with a biased catalog.
- **Calibration claim gate:** `risk_class` and any "probability of occurrence" wording are allowed only for a calibrated model on the temporal and spatial hold-outs; otherwise outputs are relative scores.

## Acceptance (to be decided with the user before any run)
Minimum margin over each baseline, maximum false-alarm rate, minimum lead time, calibration tolerance. None is set here; choosing them after seeing results is not allowed.

## Reporting
A frozen results table (model id and version, dataset hash, split file, seeds, metrics with intervals, baselines, failure analysis) stored with the model card under `models/<id>/<version>/`. Phase 10 results for the current repository: `NOT_APPLICABLE`.
