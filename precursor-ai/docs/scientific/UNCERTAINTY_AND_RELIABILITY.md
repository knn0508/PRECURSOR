# Uncertainty, quality masks and reliability conditions (Phase 8)

Status: implemented and tested on hand-made and synthetic inputs only (2026-11-15). **No model exists, so no predictive uncertainty and no explanation is produced.** Code: `backend/app/services/uncertainty/`, `backend/app/schemas/uncertainty.py`.

## 1. Uncertainty ledger (`ledger.build_report`)
A per-area `UncertaintyReport` built only from metadata Phases 2-6 already record (the Phase 5 features manifest, optionally an InSAR quality report and per-series gap counts). Every item is a recorded fact with its source phase; none is an estimate.

| Code | Rule | Source |
|---|---|---|
| `SYNTHETIC_INPUTS` | manifest `contains_synthetic_data` is true | Phase 5 manifest |
| `REAL_DATA_NOT_VALIDATED` | `real_data_validation` is not `PERFORMED` | Phase 5 manifest |
| `FEATURES_NOT_AVAILABLE` | count of NOT_AVAILABLE features (value = count) | Phase 5 manifest |
| `LAYER_SKIPPED` | a Phase 4 layer was skipped | Phase 5 manifest |
| `RESOLUTION_MISMATCH` | a layer's nominal native resolution is >= 2x coarser than the analysis grid (value = ratio) | nominal table: NASADEM 30 m, WorldCover 10 m, SoilGrids 250 m, SMAP 9 km, IMERG 0.1 degree (~11 km); nominal only |
| `TEMPORAL_GAPS` | caller-supplied missing/expected days of a series (value = % missing; never filled) | Phase 4 rainfall/SMAP counts |
| `SIGN_CONVENTION_UNVERIFIED`, `INSAR_SYNTHETIC`, `INSAR_COHERENCE_MEAN` | from the Phase 3 quality report | Phase 3 |

`predictive_uncertainty` is always `NOT_ESTIMATED` until a real model and a real method exist. An absent item means "not recorded", not "no problem". Endpoint: `GET /api/v1/uncertainty/areas/{area_id}/report` (404 until a feature extraction exists).

## 2. Quality masks (`masks.py`)
Deterministic boolean masks, **True = flagged**. They are data-quality masks, not risk. NaN input flags the cell (missing data is not usable data). Thresholds are caller-supplied and must be recorded by the caller; no universal value exists (same position as `insar/coherence.py`).
- `low_coherence_mask(coh, threshold)`: coherence below the threshold.
- `vegetation_mask(ndvi, threshold)`: NDVI at or above the threshold (dense vegetation tends to decorrelate; the value is a choice, not a law).
- `layover_shadow_masks(slope, aspect, look_azimuth, incidence)`: with range-plane slope `alpha = atan(tan(slope) * cos(aspect - (look_azimuth + 180)))` (positive = faces the sensor): layover when `alpha >= incidence`, shadow when `-alpha >= 90 - incidence`. Local terrain only; occlusion by distant relief is not modelled.
- `los_sensitivity` / `los_insensitive_mask`: cosine between the unit ground-to-sensor vector and the unit downslope motion vector (positive = toward the sensor); flagged when its magnitude is below the caller's minimum. This assumes slope-parallel motion (a simplification) and is **undefined (NaN, flagged) on flat cells**, where aspect has no meaning. Found and fixed during testing (a flat cell first returned a spurious number).
Look azimuth and incidence are caller inputs. Phase 3 records only `orbit_direction` and `wavelength_m` (verified in `insar/types.py`), so wiring them from product metadata is impossible until those fields are recorded.

## 3. Propagation (`propagation.py`)
`UncertaintySource` and `Propagator` protocols (interfaces only) and one analytic formula, the Cramer-Rao lower bound for interferometric phase noise (Rodriguez and Martin 1992; Just and Bamler 1994):
`sigma_phi = sqrt(1 - gamma^2) / (gamma * sqrt(2 N))` rad, then `sigma_d = (lambda / 4 pi) * sigma_phi` m. Checked against hand values (gamma 0.5, N 1: sqrt(1.5) = 1.2247 rad; lambda 0.24 m: 0.0233909 m). **It is a lower bound for phase noise only**: it excludes atmosphere, unwrapping errors, orbit and reference-point errors, and must never be presented as total uncertainty. `N` (effective looks) is caller-supplied because the products read so far do not record it. gamma outside (0, 1] gives NaN (not estimated), never 0. The formula (standard-deviation and variance forms) matches [an InSAR phase-denoising review](https://arxiv.org/pdf/2001.00769) and the variance form in [arXiv 2105.11544](https://arxiv.org/pdf/2105.11544) (checked 2026-11-15). The original 1992 and 1994 papers were NOT read; the attribution is taken from those secondary sources.

## 4. Reliability conditions (`reliability.suppression_reasons`)
An output (once a model exists) must be **suppressed** when any holds: inputs are synthetic (`SYNTHETIC_INPUTS`); location outside the model's `valid_region` (bbox check only) (`OUTSIDE_VALID_REGION`); time outside `valid_time` (`OUTSIDE_VALID_TIME`); valid input coverage unknown or below the caller's minimum fraction (`INSUFFICIENT_COVERAGE`; no default fraction, it is policy to set with the validation protocol). `apply_suppression` stores the reasons in the report. Not yet wired into a prediction response (no model).

## 5. Explainability
Interface only. `Explainer` protocol, `Explanation`, `FeatureContribution`; a model folder may hold `explainer.json` (`method`, `background_dataset_ref`, `scopes`). `POST /api/v1/prediction/explain` returns `MODEL_NOT_AVAILABLE` under `PREDICTION_BACKEND=none` or when no explainer is attached. Explanations describe model behaviour, not physical causation; every `Explanation` carries that caveat. No SHAP/LIME or other attribution runs anywhere in app code.
