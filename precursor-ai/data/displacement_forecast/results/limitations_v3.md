# Limitations (v3)

**Data completeness**
- F18904: 12 of 293 planned AOI subsets (Sep 2025 – Jan 2026), finalised early at the user's request because
  of link speed. There is no chained descending series, so no desc forecasting, no desc state-space model, and
  no 2024 descending coverage.
- NISAR: 10 of 16 overlap pairs (7 track-13 D, 3 track-34 A) + one Sep–Oct 2026 pair. All PROVISIONAL (CRID P05023).
- 1 of 281 F16940 subsets lacks the identification group (connection reset at ingest). Its orbit rests on the CMR record.

**Measurement physics**
- asc + desc are rank 2; north is unobservable. The core's southward downslope motion projects < 0.1 into
  either S1 LOS. LOS values in the core are a small, geometry-dependent fraction of the ground motion.
- NISAR: phase→LOS sign undocumented (signed values blocked); ionosphere, troposphere and solid-earth tide
  are not removed. The ~8 mm stratified troposphere (core vs stable) is comparable to core signals. Grids are
  80 m, versus OPERA's 30 m: block averaging over valid OPERA pixels (≥ 50 % valid) reduces OPERA noise and
  mixes heterogeneous motion.
- OPERA v1 has no tropospheric correction. v3 cross-track intervals use raw values (stable-median reference
  only), so they include atmosphere: 12-day stable MAD 2–5.5 mm (asc), 2.4–12.5 mm (desc).
- The asc and desc stable reference uses the 2016–2022 F16940 stable set for both frames. It is causal, but
  assumes the same pixels are stable in the desc look.

**Statistics / selection**
- 2024+ test was inspected in v1/v2/v3: every test number is exploratory. Validation is 2023 only.
- Bootstrap CIs resample pixels and ignore date dependence. The paired D2 vs C CI is therefore optimistic in width.
- "Strong motion" groups are label-defined and are used only for retrospective reporting (oracle diagnostic).
- Cross-sensor correlations: no CI, few pairs (9 near-parallel), spatially autocorrelated cells (effective n << 3 000).

**No independent truth**
- No on-slide GNSS, survey, or UAVSAR data were ingested: `external_ground_truth_unavailable`. Nothing in v3
  validates landslide motion or hazard prediction.
