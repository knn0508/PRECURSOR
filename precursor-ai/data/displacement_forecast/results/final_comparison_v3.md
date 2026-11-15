# PRECURSOR AI v3: final comparison (what improved, what failed, what is uncertain)

Research estimate, not a landslide warning. Run date 2026-11-15. All numbers trace to files in `results_v3/`.
At the user's request the run was finalised with partial downloads: F18904 has **12 of 293** planned AOI
subsets (Sep 2025 – Jan 2026); NISAR has **10 of 16** overlap-window pairs plus the Sep–Oct 2026 file.
The 2024 descending window was **not** downloaded.

The three output types are kept separate:
**observed** = valid satellite measurement; **inferred** = model output; **sensor limit** = not measurable.

## 1. What changed or improved (with evidence)
| # | Result | Type | Evidence |
|---|---|---|---|
| 1 | **F18904 verified**: DESCENDING, track 71, 374 v1.0 granules (2016-08-12 → 2026-03-17). It covers the AOI on the **same 30 m grid** as F16940 (no resampling). Static LOS from the product, MD5-checked | observed metadata | CMR record, probe granule, `test_f18904_…` (now runs and passes) |
| 2 | **Descending adds observed core coverage.** Nov 2025 – Mar 2026, 11 date pairs: core valid asc 15.8 %, desc 28.9 %, **union 34.7 %** (desc-only +18.9 points, 2.2× asc alone). AOI: 76.9 % → 79.6 % | observed | `observability_summary.csv`, `coverage_maps/` |
| 3 | **NISAR sees the core where OPERA cannot**: 9 of 10 overlap pairs have 84–99 % usable core cells vs ~4 % valid OPERA-asc core cells at 80 m. One pair (2026-01-22 → 02-03) has 0 % | observed (measurability, not accuracy) | `nisar_pair_audit.csv`, `cross_sensor_validation.csv` |
| 4 | **Contemporaneous NISAR–OPERA comparison became possible.** The skill assumed only a 2026 pair; CMR shows 36 provisional pairs in Nov 2025 – Mar 2026. NISAR track 13 acquires on the **same days** as S1 ascending, with LOS **17.9°** apart | observed metadata | `_cmr_nisar_gunw.json`, `cross_sensor_validation.csv` |
| 5 | **Corrected a metadata misreading.** The NISAR `*CorrectionApplied=True` flags concern **geolocation**, not phase. Ionosphere and troposphere are **not removed** from `unwrappedPhase`; empirically corr(phase, iono screen) = 0.79 | metadata fact | `nisar_metadata_audit.md` (old `results/cross_sensor_table.md` superseded) |
| 6 | **Small, consistent 12-day gain over the v2 Kalman.** The causal filter with a ministack re-referencing step (D2) was validation-selected. Test MAE 2.561 vs 2.591; paired diff **−0.030 mm [−0.031, −0.028]**; validation −0.038. Direction 0.664 vs 0.634 | inferred | `state_space_ablation.csv`, `state_space_paired_ci.json` |
| 7 | **The physical reason OPERA under-sees Portuguese Bend is now quantified.** The core's downslope direction (188°, 8.7°) projects only **+0.048 (asc) / −0.088 (desc)** into the LOS; asc + desc are blind to north | geometry fact | `geometry_identifiability.md` |
| 7b | **NISAR ascending (track 34) is the best-placed look for the slide motion**: its LOS sensitivity to the core's downslope direction is **−0.36**, ~4–7× that of Sentinel-1. Its north component (+0.167) also breaks the asc+desc north blindness when combined over the same interval | geometry fact (NISAR phase sign still unverified) | `geometry_identifiability.json` |
| 8 | Corrected GNSS facts: PVEP ended 2000 (PVE3 continues to 2026-10); **PVRS runs 1999 → 2026-10** (not "from 2026-10"); CAPE ends 2022-11 | metadata fact | `external_evidence_matrix.csv` |

## 2. What did not improve or failed
| # | Result | Evidence |
|---|---|---|
| 1 | **B0 is still the best 12-day measurement forecaster.** D2 is +0.110 mm [+0.105, +0.114] worse. B0 unchanged (hash-verified) | `state_space_paired_ci.json`, `test_existing_B0_benchmark_unchanged` |
| 2 | **Trend-branch selection failed out of sample.** The validation-best trend estimator (D2, λ = 0; val 0.815) scores **0.719** on test, below the pre-specified T1 (0.767) and D0 (0.762). Same failure as v2 OLS-72 | `state_space_ablation.csv` |
| 3 | QA-weighted noise, Huber update, change-point, and "all options" did not beat D2 on validation | `state_space_ablation.csv` |
| 4 | **Conditional E/U finds no core signal.** For 2025-11-11 → 12-29 (48 d), 125 core pixels are valid in both frames (6.4 %). 17.6 % of them exceed 2σ in U, identical to non-core (17.6 %). Median E 2.1 ± 5.1, U −0.2 ± 3.6 mm | `cross_sensor_summary.json` |
| 5 | **Slope-constrained magnitude unusable**: both sensitivities < 0.2; a 15° aspect error triples the magnitude | `geometry_identifiability.md` |
| 6 | Intervals: raw D2 cov80 0.82 overall but 0.71 moving, 0.56 core; strong motion covered by no method (≤ 0.25) | `state_space_intervals.csv` |

## 3. Scientifically uncertain (open)
| # | Question | Why open |
|---|---|---|
| 1 | Did descending observe the **2024** core when ascending lost 92 %? | 2024 desc granules not downloaded (blocker 1). **Not answered.** |
| 2 | Is the NISAR–OPERA agreement real ground motion? | All **9/9 near-parallel pairs correlate negatively** (r −0.26 … −0.69, median −0.34), but **4/5 geometry-mismatched pairs do too** (median −0.23). A shared component (vertical-dominant LOS, atmosphere, reference) is the simplest explanation. Not geometry-specific, so **not** evidence of deformation agreement |
| 3 | NISAR phase → LOS sign | Not documented. The consistent negative correlation suggests positive phase ↔ motion away from the sensor. That is an **inference**; signed NISAR displacement stays blocked |
| 4 | How much of the NISAR core |change| (median 7–29 mm per pair) is motion vs atmosphere? | Weather-model troposphere predicts ~8 mm core − stable; ionosphere not removed. Unresolved |
| 5 | Core north/south motion | Unobservable with asc + desc. Needs on-slide GNSS, optical tracking, or a third look (NISAR track 34: N = +0.167) |
| 6 | Whether D2's 0.03 mm gain holds on a fresh holdout | The 2024+ test was inspected before; a new period or frame (e.g. F36540) is needed |

## 4. Bottom line
- **Changed for real:** measurement coverage, not prediction accuracy. Adding the descending geometry
  roughly doubles the observed core area in the overlap window, and NISAR L-band keeps the core
  measurable almost everywhere. We also now know *why* Sentinel-1 cannot measure the main
  (southward) slide motion, and the NISAR correction status is correctly documented.
- **Model side:** only a marginal gain (−0.03 mm vs Kalman); B0 is not beaten; trend-direction
  selection did not transfer.
- **Not achieved:** no validated 2024 core motion, no 3-D motion, no NISAR-based ground truth,
  no improved hazard prediction.
