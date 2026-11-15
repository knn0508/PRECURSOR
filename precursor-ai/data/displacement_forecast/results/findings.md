# Findings — skill "precursor-ai-insar-quality-pipeline", batch 1 (Steps 0–1, P0)

Generated from `scripts/qa_audit.py` and the persistence check (`results/qa_persistence_check.json`). Descriptive only: no model was fitted and no threshold was tuned.

## 1. Masked landslide core (1 963 px; the earlier artifact quoted 1 958 under the previous stack)
Definition: valid ≥ 80 % of train dates and ≤ 30 % of 2024-06 → 2025-12 dates.

| Window 2024-06-19 → 2024-11-22 | share of core pixel-dates |
|---|---|
| observed (finite, recommended_mask = 1) | 6.8 % |
| **masked but finite** | **91.9 %** |
| absent (no value) | 1.3 % |

- Masked-but-finite core values fail **both** locally checkable rules: connected component = 0 in 99.0 % of cases and temporal coherence < 0.6 in 99.8 %. Phase-unwrapping / decorrelation failure is the likely cause. `phase_similarity` is not available locally.
- Loss begins in 2023-01 and is near-total from 2023-06. That is before the 2024 peak and consistent with the 2023 reactivation.
- **The masked values do not contain the acceleration.** Relaxed chaining over all finite values, re-referenced to the stable median, gives a core rate of median 0.04 mm/day and maximum 0.39 mm/day for Jun–Nov 2024. Published rates are ~14.5 mm/day (JPL UAVSAR, Sep–Oct 2024) and > 43 mm/day (city, Jul–Aug 2024). These are ground motion, not Sentinel-1 LOS, so only the order of magnitude is comparable, but a 35–100× gap remains.
- **Consequence for Step 2:** relaxing the mask in the core would inject near-zero, physically wrong labels. Masked-but-finite core values must stay class B/C and must not be used as labels. An adaptive mask cannot recover the core from these products.

Figures: `figures/qa_core_class_timeline.png`, `figures/qa_core_maps.png`, `figures/qa_layers_timeline.png`.

## 2. The +75 / −60 mm sign discrepancy (pixel row 58, col 20)
Checked and ruled out as causes:
- **Date alignment:** every label date matches a stack acquisition. Issue → target is always 12 days.
- **Sign convention:** consistent end to end. OPERA positive = towards the satellite. Labels and inputs come from the same cumulative series, so a convention error cannot flip only the predictions.
- **Data quality at this pixel:** 182/182 train dates observed; in the test period 57 observed, 9 masked-finite (excluded from labels). The pixel lies outside the core.
- **Reference changes:** 24 ministack switches, the same as everywhere. The processed and relaxed chains agree where both are valid (see `figures/qa_trace_pixel.png`).

**Cause: model anti-persistence.** The pixel moves away from the satellite in both periods: train rate −8.6 mm/yr, test labels mean −1.2 mm per 12 days. The model predicts +1.35 mm per 12 days on average.

| Pearson r, test (E3) | stable | moving | strong |
|---|---|---|---|
| label vs last input increment | −0.39 | −0.41 | −0.64 |
| **prediction vs last input increment** | **−0.76** | **−0.78** | **−0.86** |
| prediction vs label | 0.49 | 0.46 | 0.67 |

- 12-day increments share the noise of the common date d_t with opposite sign, so label and last increment are negatively correlated by construction (train r = −0.42). The model learns this reversal and applies it about twice as strongly as the data supports.
- **Per moving pixel** (≥ 10 test samples, n = 399), the sign of the mean prediction matches the sign of the mean observed motion in only **36 %** of pixels. The correlation of the means is **−0.44**. On persistent movers the model systematically predicts the opposite of the trend.
- The 6-step input window carries almost no usable trend information (label vs 6-step sum r = −0.24). It too is dominated by the shared d_t noise.

**Implication:** the overall ~12 % skill is largely noise-reversal. To get the trend right on moving pixels, the inputs need a noise-robust **long-window causal velocity** (e.g. a robust slope over the past 12–24 valid acquisitions) and an evaluation of sign agreement per moving pixel. Both belong to Step 3.

## 3. Data inventory
See `data_inventory.md`. Main blocker: phase_similarity, inversion residuals, short_wavelength_displacement, water_mask and the correction layers were not saved in our AOI subsets. Using them requires re-subsetting (~5 h).

## Status of techniques
| Technique | Status | Evidence |
|---|---|---|
| Relax recommended_mask in core | **reject** | masked core values show ≤ 0.4 mm/day vs ≥ 14.5 mm/day published |
| QA classes A/B/C + reason codes | implemented (`quality_audit.py`), tested | 19 tests pass |
| Long-window robust velocity feature | **next** (Step 3) | anti-persistence diagnosis above |
| Conformal intervals | pending (Step 7) | strong-motion coverage ~9 % |

---

# Batch 2 — Step 3 (intermittent / long-window features) and Step 7 (conformal)

Scripts: `src/precursor/temporal_features.py` (tested causal), `scripts/step3_ablation.py`. Outputs: `results/step3_ablation.csv`, `results/step3_conformal.csv`.
Matched samples for every row: val n = 133 434, test n = 304 375 (moving 16 779, strong 15 614). DL rows are the mean of 3 seeds.

## Feature ablation (test; selection on validation)
| Features | Model | val MAE | test MAE | test moving | test strong | per-pixel sign (moving) | per-pixel corr |
|---|---|---|---|---|---|---|---|
| — | zero | 3.497 | 2.790 | 3.629 | 11.013 | — | — |
| B0 base | LSTM-TCN (**val-selected**) | **3.014** | 2.451 | 3.273 | 8.701 | 0.36 | −0.44 |
| B2 +QA (phase quality, CC0) | LSTM-TCN | 3.024 | 2.473 | 3.305 | 8.885 | 0.41 | −0.28 |
| B3a +trend/gaps | LSTM-TCN | 3.076 | 2.435 | 3.252 | 8.657 | 0.45 | −0.46 |
| B3 +QA+trend/gaps | LSTM-TCN | 3.064 | 2.448 | 3.276 | 8.747 | 0.48 | −0.30 |
| B3r +…+rain | GRU | 3.084 | 2.461 | 3.276 | 8.929 | 0.50 | −0.39 |

- QA features (B2) do not help (validation and test slightly worse).
- Trend / gap features improve per-pixel sign agreement on moving pixels (0.36 → 0.45–0.50), but it stays below chance and the per-pixel correlation stays negative. Prediction vs last-increment correlation is unchanged (≈ −0.78). Validation does **not** prefer them.
- **Decision:** keep B0 as the validation-selected forecaster. Keep the temporal features as a tested, available option. Do not claim they fix the sign problem.

## Root cause: two objectives inside one target
Analytic baselines with no learned weights (window and a chosen on validation):

| Forecast | test MAE | moving MAE | per-pixel sign | per-pixel corr |
|---|---|---|---|---|
| pure trend v·h (288 d) | 2.815 | 3.657 | **0.76** | **+0.81** |
| trend − 0.75·deviation (144 d, val-selected) | 2.670 | 3.575 | 0.70 | +0.35 |
| B0 LSTM-TCN | **2.451** | **3.273** | 0.36 | −0.44 |

The 12-day increment label mixes (i) the underlying motion and (ii) the reversal of the current date's noise. MAE rewards (ii) because 94 % of samples are stable. The landslide question needs (i). Getting MAE down and getting the per-pixel motion direction right currently trade off against each other.

## Conformal intervals (val-selected B0 LSTM-TCN; calibrated on 2023 validation only)
| Method | cov all | cov stable | cov moving | cov strong* | width all (mm) | width moving (mm) |
|---|---|---|---|---|---|---|
| raw quantiles | 0.77 | 0.77 | 0.70 | 0.10 | 7.0 | 7.9 |
| CQR global | 0.87 | 0.88 | **0.80** | 0.16 | 9.1 | 10.0 |
| CQR Mondrian (moving × \|last inc\| tercile) | 0.87 | 0.87 | 0.87 | 0.18 | 9.0 | 12.3 |

*"strong" is defined by the observed label (|y| > train p95), so it is not known at forecast time. Group-conditional calibration cannot target it, and 80 % conditional coverage on that set is **not** claimed.
- CQR global brings moving-pixel coverage to the nominal 0.80 and over-covers stable pixels (test noise is lower than in 2023 validation).

## Recommendation (next)
Separate the two objectives explicitly:
1. **Trend head:** target = future velocity, an OLS slope fitted only to genuinely observed acquisitions in (t, t + 144 d]. This is a label built from observed data, not imputation, and it is excluded where fewer than N valid future points exist. Evaluate with velocity MAE, per-pixel sign and correlation, and the pure-trend baseline (0.76 / +0.81) as the bar to beat.
2. **Increment head:** the current 12-day target, kept for measurement-level forecasts with CQR intervals.

---

# Batch 3 — remaining skill items without re-download (Steps 2, 4, 5, 6, 7 and mandatory tests)

## Step 2: mask configurations (`scripts/step2_masks.py`, `results/step2_masks.csv`, `results/step2_matched.csv`)
One chained cumulative series. Each configuration changes only validity, then reruns common-mode, tropo, samples and B0 LSTM-TCN (3 seeds).

| Config | test n | coverage core Jun24–Dec25 | coverage moving ring | stable noise (mm) | own-set MAE | **matched MAE (n=181 216, original labels)** | matched moving |
|---|---|---|---|---|---|---|---|
| original (adopted) | 304 375 | 4.5 % | 56 % | 3.64 | 2.451 | **2.106** | **2.382** |
| conservative tc ≥ 0.7 | 221 688 | 1.7 % | 19 % | 3.52 | 2.239 | 2.103 | 2.425 |
| conservative tc ≥ 0.8 | 182 548 | 0.3 % | 7 % | 3.47 | 2.150 | 2.105 | 2.462 |
| adaptive CC>0, tc ≥ 0.5 | 276 032 | 5.2 % | 44 % | 3.54 | 2.346 | 2.101 | 2.454 |
| adaptive CC>0, tc ≥ 0.4 | 292 252 | 9.9 % | 57 % | 3.56 | 2.405 | 2.096 | 2.460 |

- Own-set MAE falls with stricter masks only because hard samples are dropped (the zero-motion MAE falls too). That comparison is invalid across masks.
- On matched samples all masks are equal within 0.01 mm. The original mask is best on moving pixels.
- Adaptive masks raise core coverage from 4.5 % to 9.9 %, but the batch 1 audit showed masked core values carry ≤ 0.4 mm/day (vs ≥ 14.5 published). The extra coverage is not reliable ground truth.
- **Decision:** keep the original `recommended_mask`. Conservative masks lose most moving-zone coverage without a matched gain. Adaptive masks add unreliable core values.

## Step 7 (B1 / B4) and core metrics
- B1 is identical to B0 (the pipeline already uses the strict original mask).
- **B4, tropo ablation:** without the tropo correction, stable noise is 4.73 mm vs 3.64. MAE on own labels on matched samples is 2.488 vs 2.106. LSTM-TCN own-set RMSE is 4.04 vs 3.38. Tropo stays on.
- **Core metric:** only 761 test samples fall in the core (0.25 % of the test set), with LSTM-TCN MAE 5.09 mm vs zero-motion in `step2_masks.csv`. Strong-motion core behaviour is untestable with OPERA (see batch 1).

## Step 5: edge-preserving filter (`spatial.masked_bilateral`, `results/step5_bilateral.csv`)
Mask-aware bilateral (σs 1.5 px, σr 3 or 6 mm, 5×5) on inputs only; labels raw. It is tested so that it never crosses masked pixels and keeps a 100 mm step.

| Inputs | stable input noise | moving amplitude (median) | val MAE | test MAE | moving | strong | core |
|---|---|---|---|---|---|---|---|
| raw | 3.637 | 167.7 | 3.014 | 2.451 | 3.273 | 8.701 | 5.087 |
| bilateral r3 | 3.597 | 167.3 | 3.016 | 2.455 | 3.273 | 8.685 | 5.102 |
| bilateral r6 | 3.559 | 166.7 | 3.015 | 2.457 | 3.275 | 8.671 | 5.088 |

Amplitude is preserved and there is no gain. **Rejected**, consistent with the noise being spatially correlated at 100 m – km scale.

## Step 4: physics checks (`src/precursor/physics_checks.py`)
- OPERA: unit meters → mm through an explicit, tested conversion. Sign + = towards the satellite. No tropospheric correction in the product. Ionosphere and solid-earth-tide layers are provided but not saved in our subsets. Our common-mode and tropo corrections are therefore not a double correction.
- NISAR GUNW (product v1.0.11, CRID P05023, ascending, left-looking, SNAPHU unwrapping). File flags say azimuth and range ionosphere, hydrostatic tropo and wet tropo corrections are **applied**. An ionosphere phase screen and LOS unit vectors are included. The phase-to-LOS **sign convention is not stated** in the file attributes, so `phase_to_los_mm` has no default sign and `check_sensor_comparison` refuses value-level OPERA↔NISAR comparison (no time overlap either: OPERA ends 2026-03, the NISAR pair is 2026-09/10).
- The tropo correction has not been validated externally. `OPERA_L4_TROPO-ZENITH_V1` exists in CMR (6-hourly, global, ~2 GB per file), but using it needs a new download.

## Step 6: cross-sensor table
`results/cross_sensor_table.md`: OPERA, NISAR GUNW/GCOV, UAVSAR, city reports, NGL GNSS (PVEP, CAPE, PVRS), OPERA TROPO, Sentinel-2, with quantity, unit, geometry, baseline, maturity, comparability and status.

## Mandatory tests (28 pass)
Cover: missing value never becomes a zero label; invalid target dropped; shuffled or duplicated timestamps rejected (guard inside `build_samples`); labels are increments of cumulative, not cumulative; m→mm in the stack and in the conversion helper; phase→LOS with explicit sign; sensor comparison refused until verified; bilateral never crosses masked pixels; QA classes partition correctly; causal temporal, neighbourhood and tropo features; leakage and split checks.

## Files
`results/run_config.yaml`, `results/experiments.csv` (172 rows, all groups, with sample counts), `results/cross_sensor_table.md`.

## Still open
- Blocked by the no-download constraint: phase_similarity and inversion residuals (re-subset), OPERA TROPO comparison, GNSS projection, Sentinel-2.
- Highest-value next modelling step: the trend head (separate future-velocity target). See the batch 2 recommendation.
