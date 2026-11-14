# PRECURSOR AI: Master Prompts (Landslide Early Prediction focus)

One self-contained prompt per phase. Paste a single prompt into a fresh Claude Code session at `precursor-ai/`. Run phases in order; never start the next phase on your own.

## Focus and roadmap adjustments

Product focus: **landslide early prediction** for any AOI. Two layers:

- **Susceptibility (static):** where slopes are prone to fail: terrain, soil, land cover, lithology, landslide history.
- **Trigger / early warning (dynamic):** when conditions turn dangerous: rainfall (antecedent + intensity), soil moisture, InSAR deformation velocity and its change.

**ML POLICY (current, binding on every prompt): NO machine-learning or deep-learning models are trained, fine-tuned or run in any of the 10 phases.** ML is a **placeholder** everywhere: schemas, interfaces, API contracts, and a frontend that shows **clearly labelled MOCK data** where a model output would appear. Real ML needs a separate, future stage that the user explicitly authorizes after Phase 10. No rule-based or hardcoded stand-ins are presented as predictions.

**ML SLOT (reserved place for the future model):** the project reserves a clearly defined, empty place where the user's finished model will be plugged in later WITHOUT redesigning anything. It consists of: (1) a backend package (e.g. `backend/app/services/prediction/`) holding the `Predictor` protocol, `ModelRegistry`, input/output schemas and a `NullPredictor` that returns `MODEL_NOT_TRAINED`; (2) a model artifact folder (e.g. `models/<model_id>/<version>/` with `model_card.md`, `metadata.json`, weights, feature schema, `training_data_provenance.json`), empty except for a README and a template; (3) a feature contract: model inputs are exactly the Phase 4/5 manifest + feature schema versions, validated at load time with `ModelInputSpec.validate_against`; (4) one config switch `PREDICTION_BACKEND = none | registered_model`, default `none`; the model-INPUT contract is the existing Phase 5 `ModelInputSpec` (`services/features_cv/schema.py`, with `validate_against`), reused, never redefined; (5) the same API endpoints that already exist, so enabling a model changes responses from `MODEL_NOT_TRAINED` to real output with no route or frontend contract change; (6) a frontend switch from MOCK to the real API response (the mock flag stays OFF by default (default UI shows N/A, per frontend rules; ADR-0008), the real-output components are already built and tested against the schema); (7) an integration guide `docs/architecture/ML_INTEGRATION.md` explaining step by step how to drop in a model. Nothing in the slot trains, loads weights or produces numbers until a real model is registered.

**Mock data rule:** mock/placeholder prediction values exist ONLY in the frontend (or a clearly separated mock fixture module), never in backend science code, DB, or API responses presented as real. Every mock value is visibly badged `MOCK / PLACEHOLDER: not a prediction`, cannot be mistaken for real output (watermark/banner, no real-looking calibration claims), and is trivially removable via one flag/module.

The 10 phases, names and order are **kept**. Scope changes for early prediction (authorized by the user on 2026-11-14; apply them to `ROADMAP.md` and the phase docs when the matching prompt runs):

| # | Change | Why |
|---|---|---|
| 1 | **Phase 4** also integrates SMAP soil moisture, lithology/geology, NDVI/vegetation and distance-to-river/fault/road features (all AOI-generic) | Early prediction needs trigger + conditioning factors that the original list lacks. SMAP is already acquired in Phase 2 |
| 2 | **Phase 5** also builds the **labelled sample dataset** (landslide / non-landslide points, spatial-block splits, no leakage) as a data product, still no training | Future models need labels; this is data engineering, not ML |
| 3 | **Phase 7** stays architecture/contracts only: two model heads (susceptibility, trigger), schemas, API returning `MODEL_NOT_TRAINED`, validation protocol docs | ML deferred; contracts make future integration drop-in |
| 4 | **Phase 8** uncertainty/explainability = interfaces and data-quality metadata only. **Phase 9** may show labelled mock prediction views. **Phase 10** documents the early-warning validation protocol (temporal hold-out, hit/false-alarm rate, lead time) as NOT_APPLICABLE until a real model exists | Scientific honesty for a warning product |

**ML TRACK EXCEPTION (2026-11-15):** the user authorized a SEPARATE ML development track (M0-M9, last section of this file) that builds models under `ml/` outside the 10 phases. It does not change the 10 phases, which remain ML-free, and nothing from it is wired into the backend/frontend/API/DB until the user decides.

**Future ML gate (NOT part of this roadmap; listed only so the contracts are designed for it):** a later, separately authorized stage requires a real dated inventory, real Phase 4-6 feature layers, an approved validation protocol, and an approved model family and compute budget.

Everything else in the global rules (scientific integrity, geographic independence, no unapproved downloads, incremental development) is unchanged.

## Shared rules block (already embedded in every prompt below)

NO ML/DL training or inference in any phase; ML = placeholders; mock prediction data only in the frontend and always labelled MOCK. Read `CLAUDE.md`, `docs/project/PROJECT_STATUS.md`, `NEXT_STEPS.md`, the phase doc and `.claude/rules/*` first. Verify earlier claims against code and tests. Reuse existing services; no rewrites of working Phase 1-3 code. No download or Earthdata login without the user approving specific files (name, source, size, AOI). Label synthetic data; never fabricate measurements, scores, probabilities or forecasts; unverified = `UNKNOWN` / `NOT_VERIFIED`. No hardcoded country/CRS/extent/dates. Test before claiming done; record real test output. Update ALL project docs after the phase (status, next steps, task log, changelog, phase doc, architecture/science/ADR/memory as needed); see the MANDATORY DOCS CLOSE-OUT in each prompt.

---

## Phase 1: Project Foundation & Architecture (close-out audit)

```text
You are working on PRECURSOR AI (precursor-ai/), a landslide early-prediction platform built from SAR/InSAR and environmental data.

TASK: Phase 1 is marked COMPLETED. Run a read-only close-out audit, fix only real defects, and make the foundation ready for the early-prediction roadmap.

Session start: read CLAUDE.md, docs/project/PROJECT_STATUS.md, NEXT_STEPS.md, docs/phases/PHASE_01.md, docs/architecture/*, .claude/rules/*.

Do:
1. Verify with commands, not docs: `docker compose up -d --build`, `/health`, `alembic upgrade head` + `alembic check` (no drift), backend pytest (throwaway PostGIS DB via TEST_DATABASE_URL, Earthdata env vars unset), frontend `tsc --noEmit`, `npm test`, `npm run lint`, `npm run build`.
2. Confirm AOIs are generic: grep for hardcoded Baku/Panama/country/CRS/extent in backend/app and frontend; report each hit, fix only if it is logic (not a test label).
3. Reconcile documentation conflicts (e.g. PROJECT_STATUS says phases 4-10 NOT_STARTED while PHASE_04.md says PARTIALLY_COMPLETED). Make PROJECT_STATUS the truth.
4. Add the "landslide early prediction" product statement and the susceptibility vs trigger split to docs/architecture/SYSTEM_OVERVIEW.md (docs only).
5. Report the known Phase 2 security issue #1 (file_path import reads arbitrary server paths); do not fix unless asked.

Constraints: no feature work, no schema change, no new dependencies, no ML. No git commits unless I ask.
Output: a table of check -> real result, defects found/fixed, docs updated, and what you did not verify.
MANDATORY DOCS CLOSE-OUT (the phase is NOT finished until done; follow .claude/rules/documentation.md). Update in this order, with real test output, dates and counts, never expected results: (1) docs/project/PROJECT_STATUS.md (phase status label + evidence, components, test results, known bugs); (2) docs/project/NEXT_STEPS.md; (3) docs/project/TASK_LOG.md; (4) CHANGELOG.md; (5) docs/phases/PHASE_NN.md (completion evidence, limitations, verification table); (6) docs/architecture/* and docs/scientific/* if design or science changed; (7) docs/adr/ for new decisions; (8) docs/project/PROJECT_MEMORY.md for durable lessons; (9) docs/project/ROADMAP.md only if scope changed as authorized. Fix contradictions between docs. Do not mark COMPLETED without evidence. End your report with a list of every doc file updated.
```

---

## Phase 2: Satellite Data Acquisition (live verification)

```text
You are working on PRECURSOR AI (precursor-ai/). Phase 2 (data acquisition) is code-complete but PARTIALLY_COMPLETED: no authenticated login or real download has ever been performed.

TASK: Make Phase 2 deliver what early prediction needs, then verify it live, but only after I approve specific files.

Session start: read CLAUDE.md, PROJECT_STATUS.md, NEXT_STEPS.md, docs/phases/PHASE_02.md, docs/phase-2-data-acquisition.md, docs/earthdata-authentication.md, docs/nasa-data-sources.md.

Step A (no network, no credentials):
1. Fix the open Phase 2 issues in PROJECT_STATUS that block real use, each with a regression test: #1 restrict `file_path` import to a configured data root; #2 credential pre-check on POST /downloads; #7 retry_job resets attempts; #8 test isolation (clear Earthdata env vars in fixtures); #5 file naming prefix with dest_dir; #6 ASF request timeout and correct source name.
2. Confirm the provider set covers early-prediction inputs: NISAR GUNW/GCOV/GSLC/GOFF, Sentinel-1 fallback, NASADEM, GPM IMERG (daily AND half-hourly for storm-scale triggers), SMAP soil moisture, NASA Global Landslide Catalog. Add NO new provider unless a gap is proven; propose in writing instead (e.g. USGS, SoilGrids and WorldCover belong to Phase 4).
3. Verify assumptions flagged UNVERIFIED (NISAR HDF5 keys, GPM mapping, catalog date order MM/DD) only against official documentation; cite the URL; otherwise leave UNKNOWN.

Step B (STOP and ask me first): present a download proposal: dataset, exact file names, size, AOI (bbox, <= 5 degrees), date range, disk/time estimate. Suggested minimum: landslide catalog CSV, 1-2 NASADEM tiles, a few IMERG daily files, one SMAP granule, one NISAR GUNW (1.2-2 GB). Wait for my explicit approval and AOI.

Step C (after approval only): run `python -m app.cli status`, dry-run discover, download approved files only, validate (VALIDATED = file integrity only), review manifests. Never print credentials.

Constraints: no ML, no Phase 3+ work, no unrelated refactors. Record real command output.
Output: fixes + tests, live results or "not performed", updated PROJECT_STATUS / PHASE_02 verification table.
MANDATORY DOCS CLOSE-OUT (the phase is NOT finished until done; follow .claude/rules/documentation.md). Update in this order, with real test output, dates and counts, never expected results: (1) docs/project/PROJECT_STATUS.md (phase status label + evidence, components, test results, known bugs); (2) docs/project/NEXT_STEPS.md; (3) docs/project/TASK_LOG.md; (4) CHANGELOG.md; (5) docs/phases/PHASE_NN.md (completion evidence, limitations, verification table); (6) docs/architecture/* and docs/scientific/* if design or science changed; (7) docs/adr/ for new decisions; (8) docs/project/PROJECT_MEMORY.md for durable lessons; (9) docs/project/ROADMAP.md only if scope changed as authorized. Fix contradictions between docs. Do not mark COMPLETED without evidence. End your report with a list of every doc file updated.
```

---

## Phase 3: SAR Image Processing & InSAR Analysis (real-data verification)

```text
You are working on PRECURSOR AI (precursor-ai/). Phase 3 (InSAR) is implemented and tested on SYNTHETIC data only. REAL_DATA_VALIDATION: NOT_PERFORMED.

TASK: Verify and harden the InSAR pipeline on a real NISAR GUNW and make its outputs usable as early-prediction inputs (velocity, coherence, quality), without claiming risk.

Session start: read CLAUDE.md, PROJECT_STATUS.md, NEXT_STEPS.md, docs/phases/PHASE_03.md, docs/scientific/INSAR_METHODOLOGY.md, DEFORMATION_METRICS.md, ADR-0004.

Prerequisite: a real GUNW file placed locally by Phase 2 with my approval. If none exists, STOP and tell me; do not substitute synthetic data as "real".

Do:
1. `REAL_INSAR_FILE=<path> pytest backend/tests/manual/test_real_insar.py -s`; read the inspection output; fix adapter mismatches (dataset paths, units, identification, polarization) with one regression test per fix.
2. Verify the phase sign convention and unwrapped/differential assumption against the current official product spec (JPL D-102272); only then change SIGN_CONVENTION_VERIFIED. Cite the source.
3. Wire what is cheap and scientifically justified: GSLC pair interferogram into runs; two-product velocity exposure. Do NOT write a phase unwrapper from scratch; if SNAPHU/SNAP/ISCE are required, write an ADR proposal and stop.
4. Time-series readiness (for Phase 6): ensure every product records acquisition date(s), reference/secondary dates, temporal baseline, orbit/track/frame, look direction, reference point, units, CRS, and QA/coherence summary. Add missing metadata fields only.
5. Process the real GUNW through the API; inspect quality report; record REAL_DATA_VALIDATION honestly (PERFORMED / PARTIAL / NOT_PERFORMED). Measure memory and time in the Docker container.
6. Keep the language: LOS displacement != vertical; velocity != acceleration; a deformation map is NOT a landslide risk map.

Constraints: no ML, no risk output, no dashboard beyond the existing minimal /dashboard/insar page.
Output: real results table, discrepancies found/fixed, updated docs and status labels.
MANDATORY DOCS CLOSE-OUT (the phase is NOT finished until done; follow .claude/rules/documentation.md). Update in this order, with real test output, dates and counts, never expected results: (1) docs/project/PROJECT_STATUS.md (phase status label + evidence, components, test results, known bugs); (2) docs/project/NEXT_STEPS.md; (3) docs/project/TASK_LOG.md; (4) CHANGELOG.md; (5) docs/phases/PHASE_NN.md (completion evidence, limitations, verification table); (6) docs/architecture/* and docs/scientific/* if design or science changed; (7) docs/adr/ for new decisions; (8) docs/project/PROJECT_MEMORY.md for durable lessons; (9) docs/project/ROADMAP.md only if scope changed as authorized. Fix contradictions between docs. Do not mark COMPLETED without evidence. End your report with a list of every doc file updated.
```

---

## Phase 4: Environmental & Geospatial Data Integration (finish, early-prediction scope)

```text
You are working on PRECURSOR AI (precursor-ai/). Phase 4 code exists under backend/app/services/environmental/ (dem, rainfall, soil, land_cover, historical_events, seismic, features, pipeline, preview) plus migration 0004 and /api/v1/environmental/*, /dashboard/environmental. It is tested on SYNTHETIC data only. Docs disagree on its status (PROJECT_STATUS says NOT_STARTED, PHASE_04.md says PARTIALLY_COMPLETED): first make them match reality.

GOAL: finish Phase 4 so it produces a harmonized, AOI-generic, provenance-tracked feature stack for landslide early prediction: SUSCEPTIBILITY factors (static) and TRIGGER factors (dynamic).

Session start: read CLAUDE.md, PROJECT_STATUS.md, NEXT_STEPS.md, docs/phases/PHASE_04.md, ADR-0005, docs/scientific/{ENVIRONMENTAL_DATA_SOURCES,TERRAIN_METHODOLOGY,RAINFALL_METHODOLOGY,SCIENTIFIC_LIMITATIONS}.md, .claude/rules/{geospatial,scientific-integrity}.md. Then inventory what exists vs the list below by running the tests and reading the code; do not rewrite working modules.

Complete / add (reuse existing patterns, one stage each in the existing pipeline, same DONE/PARTIAL/NOT_AVAILABLE/SKIPPED/FAILED semantics):
STATIC (susceptibility):
 - NASADEM elevation; slope, aspect (Horn), plus curvature and TWI/flow accumulation only if justified and tested.
 - Soil (SoilGrids), land cover (WorldCover / MCD12Q1), NDVI/vegetation if a source file is provided.
 - Lithology/geology: ingest a user-provided geology vector/raster; output class ids with the source legend preserved. No invented lithology.
 - Distance to rivers / faults / roads from user-provided vectors (metric CRS, no degrees-as-metres).
 - Historical landslides (NASA GLC via Phase 2 table) and USGS seismicity (PGA/event counts as descriptive stats only).
DYNAMIC (triggers):
 - Rainfall: IMERG daily (and half-hourly if present): 1/3/7/14/30-day accumulation, antecedent rainfall, max intensity, as DESCRIPTIVE time-indexed statistics. No thresholds, no alerts.
 - SMAP soil moisture: AOI statistics + time series, with native resolution (~9-36 km) and quality flags stated.
 - Phase 3 InSAR: reference only valid REAL products (synthetic/unverified excluded and labelled).
COMMON:
 - Standardise CRS, align grids on a chosen reference grid, clip to AOI, resample method per data type (continuous: bilinear; categorical: nearest), nodata propagation, per-layer lineage and quality (coverage %, missing, resolution, date range).
 - Export a harmonized stack manifest (layer id, type=static|dynamic, units, CRS, resolution, source, date range, provenance, synthetic flag) consumable by Phase 5.
 - AOI generic: no hardcoded country/CRS/extent/dates; test with at least two AOIs in different UTM zones, one crossing a UTM zone boundary, and one smaller than a raster cell.

Tests: unit tests per stage with synthetic fixtures (labelled), edge cases (empty AOI, missing tiles, all-nodata, antimeridian rejected, mixed CRS), migration up/down/up + `alembic check`, pytest green with Earthdata vars unset, frontend tsc/test/lint/build.
Real data: only if I approve specific files; present dataset, size, AOI first. Otherwise status stays IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA.

Forbidden: ML, risk scores, susceptibility classes, thresholds, "danger" language, rule-based predictions, the full Phase 9 dashboard.
Output: gap list (planned vs found), what you added, real test output, stack manifest example (labelled synthetic), updated docs and statuses, remaining unverified assumptions.
MANDATORY DOCS CLOSE-OUT (the phase is NOT finished until done; follow .claude/rules/documentation.md). Update in this order, with real test output, dates and counts, never expected results: (1) docs/project/PROJECT_STATUS.md (phase status label + evidence, components, test results, known bugs); (2) docs/project/NEXT_STEPS.md; (3) docs/project/TASK_LOG.md; (4) CHANGELOG.md; (5) docs/phases/PHASE_NN.md (completion evidence, limitations, verification table); (6) docs/architecture/* and docs/scientific/* if design or science changed; (7) docs/adr/ for new decisions; (8) docs/project/PROJECT_MEMORY.md for durable lessons; (9) docs/project/ROADMAP.md only if scope changed as authorized. Fix contradictions between docs. Do not mark COMPLETED without evidence. End your report with a list of every doc file updated.
```

---

## Phase 5: Computer Vision & Feature Extraction (+ labelled dataset)

```text
You are working on PRECURSOR AI (precursor-ai/). Phase 4 must be at least PARTIALLY_COMPLETED with a harmonized stack manifest. If it is not, STOP and say so.

GOAL: build a reusable, AOI-generic feature-extraction pipeline and a LEAKAGE-SAFE LABELLED SAMPLE DATASET for future landslide early-prediction models. No training, no inference.

Session start: read CLAUDE.md, PROJECT_STATUS.md, NEXT_STEPS.md, docs/phases/PHASE_05.md, ADR-0002 and ADR-0005, ai_engine/computer_vision/README.md, ai_engine/preprocessing/README.md. Decide with an ADR whether code lives in backend/app/services/features_cv/ (recommended, matches ADR-0004/0005 precedent) or ai_engine/.

Build:
1. Raster preprocessing: tiling/windowing with CRS/transform preserved, normalisation that records its parameters, nodata handling, no silent resampling.
2. Image/terrain-derived features via OpenCV/scikit-image/SciPy: local relief, roughness, curvature, edge/lineament density, texture (GLCM), slope-break; change-detection features (NDVI difference, coherence change, InSAR velocity gradient) only when two dated real inputs exist.
3. Optical imagery is out of scope unless a source is approved; define the interface only.
4. Feature schema: name, dimension, units, window/scale, source layers, CRS, resolution, date, provenance, synthetic flag. Versioned (schema_version). A `FeatureExtractor` protocol and registry.
5. LABELLED DATASET BUILDER (data product, not ML): from the Phase 4 landslide inventory build positives (event locations with date and location-accuracy radius) and documented negative sampling (outside buffer, same region, stratified); store event date so dynamic features can be sampled at lead times before the event. Provide spatial-block and temporal splits, with a leakage test (no train/test overlap within buffer or time window), class balance report, and an explicit "inventory bias" caveat (catalog is media/report-derived, incomplete).
6. Model interface placeholders: `ModelInputSpec`, tensor/array exporters (Parquet/NumPy/COG) and a PyTorch Dataset interface behind an optional import, NOT trained, NOT run.

Tests: determinism, CRS/transform preservation, nodata propagation, schema validation, leakage test, empty/small AOI, two AOIs in different UTM zones. Use labelled synthetic fixtures.

Forbidden: training, fine-tuning, inference, pretrained-weight scoring, any risk score or label produced by a rule.
Output: modules, ADR, schema docs, real test output, a sample (labelled synthetic) dataset manifest, updated docs and statuses.
MANDATORY DOCS CLOSE-OUT (the phase is NOT finished until done; follow .claude/rules/documentation.md). Update in this order, with real test output, dates and counts, never expected results: (1) docs/project/PROJECT_STATUS.md (phase status label + evidence, components, test results, known bugs); (2) docs/project/NEXT_STEPS.md; (3) docs/project/TASK_LOG.md; (4) CHANGELOG.md; (5) docs/phases/PHASE_NN.md (completion evidence, limitations, verification table); (6) docs/architecture/* and docs/scientific/* if design or science changed; (7) docs/adr/ for new decisions; (8) docs/project/PROJECT_MEMORY.md for durable lessons; (9) docs/project/ROADMAP.md only if scope changed as authorized. Fix contradictions between docs. Do not mark COMPLETED without evidence. End your report with a list of every doc file updated.
```

---

## Phase 6: Time Series Analysis & Deformation Forecasting (deterministic indicators)

```text
You are working on PRECURSOR AI (precursor-ai/). Requires Phase 3 products with dates and Phase 4/5 dynamic layers. If real multi-date data is absent, build and test on SYNTHETIC series (labelled) and keep statuses honest.

GOAL: turn dynamic observations into analysis-ready time series and deterministic trigger indicators for early prediction. Statistical description only; no ML forecasting, no fabricated future values.

Session start: read CLAUDE.md, PROJECT_STATUS.md, NEXT_STEPS.md, docs/phases/PHASE_06.md, docs/scientific/DEFORMATION_METRICS.md, RAINFALL_METHODOLOGY.md, ai_engine/time_series/README.md.

Build:
1. Chronological series store per AOI/pixel/zone: deformation (LOS mm, velocity), coherence, rainfall, soil moisture; each point keeps source, sensor, geometry (track/look), quality, synthetic flag.
2. Gap and irregular-interval analysis; never interpolate silently. Any gap filling is optional, explicit, labelled, and excluded by default.
3. Deterministic indicators with documented formulas: linear trend with confidence interval (statsmodels), Theil-Sen, Mann-Kendall, velocity change between windows, acceleration ONLY where >= N compatible acquisitions exist (state N), rainfall antecedent indices (1/3/7/14/30-day, API), event detection descriptive (storm count, peak intensity, duration), cross-correlation/lag between rainfall and deformation as a DESCRIPTIVE statistic with caveats (correlation != causation).
4. Mixed-geometry guard: ascending vs descending LOS and different sensors are never merged into one series without an explicit documented decomposition.
5. Forecasting INTERFACE only: `Forecaster` protocol, input/output schemas, horizon, uncertainty fields, `NotImplementedForecaster` returning a clear NOT_IMPLEMENTED status. No baseline persistence/linear extrapolation presented as "forecast".
6. Limitations report per series: n observations, span, median interval, gaps, missing fraction, aliasing risk.
7. Minimal test page only (Recharts) if needed; no full dashboard.

Tests: synthetic known-trend recovery (tolerance stated), gap handling, irregular sampling, short series refusal, mixed-geometry refusal.
Forbidden: ML forecasting, extrapolated future deformation, rainfall "thresholds" used as alerts, risk labels.
Output: modules, schemas, real test output, limitations docs, updated statuses.
MANDATORY DOCS CLOSE-OUT (the phase is NOT finished until done; follow .claude/rules/documentation.md). Update in this order, with real test output, dates and counts, never expected results: (1) docs/project/PROJECT_STATUS.md (phase status label + evidence, components, test results, known bugs); (2) docs/project/NEXT_STEPS.md; (3) docs/project/TASK_LOG.md; (4) CHANGELOG.md; (5) docs/phases/PHASE_NN.md (completion evidence, limitations, verification table); (6) docs/architecture/* and docs/scientific/* if design or science changed; (7) docs/adr/ for new decisions; (8) docs/project/PROJECT_MEMORY.md for durable lessons; (9) docs/project/ROADMAP.md only if scope changed as authorized. Fix contradictions between docs. Do not mark COMPLETED without evidence. End your report with a list of every doc file updated.
```

---

## Phase 7: Predictive Risk Assessment Engine (architecture and placeholders only)

```text
You are working on PRECURSOR AI (precursor-ai/). This phase defines the landslide early-prediction engine ARCHITECTURE. NO ML is trained or run; the model is a placeholder.

Session start: read CLAUDE.md, PROJECT_STATUS.md, NEXT_STEPS.md, docs/phases/PHASE_07.md, ADR-0002 (ML deferral), the Phase 5 dataset docs, Phase 6 indicator docs, ai_engine/risk_assessment/README.md.

PART A (always allowed): architecture and contracts.
1. Define two model heads: (a) SUSCEPTIBILITY (static, per-cell, "where"), (b) TRIGGER/EARLY-WARNING (dynamic, per-cell-per-time, "when", with a stated lead time and horizon). Define analysis units (grid cell size, time step), target definitions (event within X days / Y metres), and the label-quality caveats.
2. Pydantic schemas and API contracts: `RiskModelInput`, `RiskModelOutput` (probability, class, calibration info, uncertainty, model_id, version, training-data provenance, valid-region/valid-time), `ModelRegistry` entry, `Predictor` protocol. Output endpoints return `NOT_AVAILABLE` / `MODEL_NOT_TRAINED` (no model exists). Mock prediction data is NOT created in the backend (the TEST_DOUBLE exists only in tests); the frontend (Phase 9) owns labelled mock data.
3. Define risk categories only as a scientific interpretation doc tied to calibrated probabilities (to be fixed after validation), not as thresholds in code.
4. Document training-data requirements, validation protocol (spatial block CV + temporal hold-out, baselines: logistic regression, rainfall-only model), metrics for rare events (PR-AUC, recall at fixed false-alarm rate, Brier score, calibration curve), class imbalance handling and the inventory-bias caveat.
5. BUILD THE ML SLOT described in the header: `services/prediction/` with `Predictor` protocol, `NullPredictor`, `ModelRegistry` (reads `models/<model_id>/<version>/metadata.json`, builds a `ModelInputSpec` from it and calls the EXISTING `ModelInputSpec.validate_against` (do not create a second input schema; `RiskModelInput` must wrap/reference `ModelInputSpec`), refuses models without model card, provenance, valid region/time), `PREDICTION_BACKEND` config (default `none`), model artifact folder with README + template files (no weights), endpoints `/api/v1/prediction/status|models|susceptibility|trigger` returning `MODEL_NOT_TRAINED` under `none`, a contract test using a TEST-ONLY dummy predictor (lives under tests/, returns a constant, labelled TEST_DOUBLE, never importable from app code) to prove the swap path works end-to-end without changing the API/schema, and docs/architecture/ML_INTEGRATION.md (how to add a model, required files, schema versioning, validation checklist, how to switch the flag, how the frontend flips from mock to real).
6. ADR-0008 already records the ML-slot decision (ADR-0002 stays unchanged); update ADR-0008 only if the design changes; document the future ML gate (real dated inventory, real Phase 4-6 features, approved validation protocol, approved model family/compute) as a requirement for a later separately authorized stage.

FORBIDDEN: training, fine-tuning, inference, any model artifact, rule-based or hardcoded substitutes for model output, fabricated scores/probabilities/classes.
Output: contracts, ADR updates, tests (schema validation, NOT_AVAILABLE behaviour), real test output.
MANDATORY DOCS CLOSE-OUT (the phase is NOT finished until done; follow .claude/rules/documentation.md). Update in this order, with real test output, dates and counts, never expected results: (1) docs/project/PROJECT_STATUS.md (phase status label + evidence, components, test results, known bugs); (2) docs/project/NEXT_STEPS.md; (3) docs/project/TASK_LOG.md; (4) CHANGELOG.md; (5) docs/phases/PHASE_NN.md (completion evidence, limitations, verification table); (6) docs/architecture/* and docs/scientific/* if design or science changed; (7) docs/adr/ for new decisions; (8) docs/project/PROJECT_MEMORY.md for durable lessons; (9) docs/project/ROADMAP.md only if scope changed as authorized. Fix contradictions between docs. Do not mark COMPLETED without evidence. End your report with a list of every doc file updated.
```

---

## Phase 8: Uncertainty Quantification & Explainability

```text
You are working on PRECURSOR AI (precursor-ai/). Early-warning output without uncertainty and explanation is not trustworthy.

Session start: read CLAUDE.md, PROJECT_STATUS.md, NEXT_STEPS.md, docs/phases/PHASE_08.md, Phase 7 docs, ai_engine/uncertainty/README.md and ai_engine/explainability/README.md.

Scope: interfaces and metadata only (no model exists). Plug into the ML SLOT: `Explainer` registered per model in the same registry/artifact folder (e.g. `explainer.json` + background dataset reference), returning `MODEL_NOT_AVAILABLE` under `PREDICTION_BACKEND=none`.
1. Uncertainty ledger: propagate data-quality metadata from Phases 2-6 (coverage, resolution mismatch, temporal gaps, InSAR coherence/decorrelation, sign-convention-unverified flags, synthetic flags) into a per-output `UncertaintyReport` schema.
2. Coverage and limitation maps: where inputs are missing/low quality (e.g. low coherence, vegetated pixels, radar layover/shadow, steep slopes unfavourable to LOS), as deterministic masks with documented rules. These are data-quality masks, not risk.
3. Uncertainty propagation interface: `UncertaintySource`, `Propagator` protocol; analytic propagation only where formulas are known (e.g. phase->LOS displacement from coherence-based phase std), citing the method.
4. Explainability interface: `Explainer` protocol, `FeatureContribution` and `Explanation` schemas, global vs local, background dataset reference, model_id link. Returns `MODEL_NOT_AVAILABLE` (placeholder; no model).
5. Reliability conditions doc: when an output must be suppressed (e.g. outside model valid-region/time, insufficient coverage).

FORBIDDEN: SHAP/LIME on a placeholder, synthetic or rule-based model; fabricated explanations; confidence numbers not derived from a real method.
Tests: schema validation, mask determinism, propagation formula against hand-computed values, MODEL_NOT_AVAILABLE behaviour.
Output: modules, docs, real test output, updated statuses.
MANDATORY DOCS CLOSE-OUT (the phase is NOT finished until done; follow .claude/rules/documentation.md). Update in this order, with real test output, dates and counts, never expected results: (1) docs/project/PROJECT_STATUS.md (phase status label + evidence, components, test results, known bugs); (2) docs/project/NEXT_STEPS.md; (3) docs/project/TASK_LOG.md; (4) CHANGELOG.md; (5) docs/phases/PHASE_NN.md (completion evidence, limitations, verification table); (6) docs/architecture/* and docs/scientific/* if design or science changed; (7) docs/adr/ for new decisions; (8) docs/project/PROJECT_MEMORY.md for durable lessons; (9) docs/project/ROADMAP.md only if scope changed as authorized. Fix contradictions between docs. Do not mark COMPLETED without evidence. End your report with a list of every doc file updated.
```

---

## Phase 9: Interactive Geospatial Dashboard (early-warning workspace)

```text
You are working on PRECURSOR AI (precursor-ai/). Frontend: Next.js 16, React 19, TypeScript, Tailwind v4, MapLibre, Recharts, shadcn/ui, vitest.

GOAL: the unified scientific dashboard. It shows REAL, SYNTHETIC and PLACEHOLDER content with unmistakable labels, and shows prediction views as clearly labelled MOCK placeholders, since no ML model exists.

Session start: read CLAUDE.md, PROJECT_STATUS.md, NEXT_STEPS.md, docs/phases/PHASE_09.md, .claude/rules/frontend.md, existing pages (/dashboard, /dashboard/insar, /dashboard/environmental, Phase 2 data pages). Reuse their components, API clients and map code; consolidate, don't duplicate. Invoke the frontend-design / ui-ux-pro-max skills as needed. Keep the cinematic landing page untouched.

Build:
1. Map workspace: AOI draw/upload/select (any region), layer manager with opacity, legend, units, CRS/resolution/date on each layer; time slider for dynamic layers.
2. Panels: satellite data inventory; acquisition & processing job monitor; InSAR displacement/velocity/coherence; terrain (slope, aspect); rainfall and soil-moisture series (Recharts); historical landslides and earthquakes; dataset metadata + quality + lineage.
3. Early-warning area (PLACEHOLDER with MOCK data, wired for the ML SLOT): build BOTH the mock path and the real-response path (probability/class, calibration note, valid region/time, uncertainty, explanation, model-card link) against the Phase 7 schemas; the real path is tested with fixture responses labelled TEST_FIXTURE and activates automatically when the API stops returning MODEL_NOT_TRAINED. susceptibility layer and trigger-forecast view built against the Phase 7 schemas. Backend returns MODEL_NOT_TRAINED; the frontend swaps in a separate mock fixture module (single flag, e.g. NEXT_PUBLIC_USE_MOCK_PREDICTIONS, default OFF so the default UI shows N/A) so the UI, legends, time slider, uncertainty and explanation panels can be designed and tested. Every mock element carries a persistent `MOCK DATA: NOT A PREDICTION` banner/watermark and badge, mock values are generated from a fixed seed, never derived from real inputs or rules, use a neutral palette (no red/amber/green risk semantics), and are never exported/downloaded as data. Show the "research prototype, not an official warning" notice. Real data panels (InSAR, terrain, rainfall) stay real and are never mixed visually with mock layers.
4. Source badges on every layer: REAL_SATELLITE | REAL_DERIVED | SYNTHETIC_DEMO | STATISTICAL | MODEL_PREDICTION | PLACEHOLDER.
5. Loading, empty, error states; accessibility (keyboard, contrast, aria on map controls), responsive, large-raster performance (tiles/COG, downsampled previews).
6. Backend additions only where the UI needs them (thin read endpoints).

Tests: vitest for helpers/state, component tests that mock layers always show the banner/badge and disappear when the flag is off, `tsc --noEmit`, lint, build, one real headless-browser run against the live stack (record what you saw).
FORBIDDEN: unlabelled mock values, mock data in the backend/DB/API, mock values presented as or derived from real results, hiding synthetic/mock labels, red/amber/green risk styling.
Output: pages/components, screenshots description, real test output, updated docs and statuses.
MANDATORY DOCS CLOSE-OUT (the phase is NOT finished until done; follow .claude/rules/documentation.md). Update in this order, with real test output, dates and counts, never expected results: (1) docs/project/PROJECT_STATUS.md (phase status label + evidence, components, test results, known bugs); (2) docs/project/NEXT_STEPS.md; (3) docs/project/TASK_LOG.md; (4) CHANGELOG.md; (5) docs/phases/PHASE_NN.md (completion evidence, limitations, verification table); (6) docs/architecture/* and docs/scientific/* if design or science changed; (7) docs/adr/ for new decisions; (8) docs/project/PROJECT_MEMORY.md for durable lessons; (9) docs/project/ROADMAP.md only if scope changed as authorized. Fix contradictions between docs. Do not mark COMPLETED without evidence. End your report with a list of every doc file updated.
```

---

## Phase 10: Testing, Validation & Deployment

```text
You are working on PRECURSOR AI (precursor-ai/). GOAL: prove what works, state what does not, and make the platform deployable.

Session start: read CLAUDE.md, PROJECT_STATUS.md, NEXT_STEPS.md, docs/phases/PHASE_10.md, docs/scientific/SCIENTIFIC_LIMITATIONS.md, all phase docs' verification tables. Re-run everything; trust no earlier report.

Do:
1. Test pyramid: unit, integration (API + PostGIS), e2e (Playwright: AOI -> search -> inventory -> processing job -> layers -> MODEL_NOT_TRAINED state and labelled MOCK view; verify mock banner always present and no mock data leaks into API/DB). Coverage report; every Phase 2-9 bug listed in PROJECT_STATUS closed or explicitly accepted.
2. Scientific validation: geospatial calculations vs hand-computed/analytic cases (slope on a known plane, area/distance in metric CRS, CRS round-trips); InSAR vs a reference (known-motion site or published product) with RMSE/bias and stated tolerance; data acquisition on real files (checksum/size/manifest). Record REAL_DATA_VALIDATION per phase as PERFORMED / PARTIAL / NOT_PERFORMED.
3. Early-warning validation: NO model exists, so write the protocol and mark results NOT_APPLICABLE. Protocol: temporal hold-out and spatial hold-out region, hit rate / false-alarm rate / precision / PR-AUC / Brier / calibration, lead-time analysis, comparison to the rainfall-threshold and rainfall-only baselines, confidence intervals, failure-case analysis, performance under inventory-bias.
4. Robustness: multiple AOIs on different continents/UTM zones, antimeridian rejection, missing data, corrupted files, interrupted downloads, restart recovery of jobs, large raster memory/time, concurrency, DB load.
5. Security: secrets handling (no credentials in logs/images/repo), path traversal (Phase 2 issue #1), input validation, dependency audit (pip-audit, npm audit), CORS, auth for write/processing endpoints, rate limiting, container hardening (non-root, minimal image).
6. ML slot checks: PREDICTION_BACKEND=none returns MODEL_NOT_TRAINED everywhere; docs/architecture/ML_INTEGRATION.md is accurate and followed in a dry run with the TEST_DOUBLE; no weights or fabricated outputs ship.
6b. Operations: structured logging, error envelope consistency, health/readiness, backups for the DB and data volumes, Alembic upgrade/downgrade, Docker Compose production profile, .env.example, CI pipeline (lint, types, tests, build, migration check), deployment and runbook docs, user docs.
7. Final scientific limitations and validation report: what was validated, against what, with what error; what was not; known biases (inventory, resolution, geometry, vegetation decorrelation); intended use and non-use ("research prototype, not an operational warning system").

Constraints: no new features beyond fixes; no downloading large real data without my approval (present dataset, size, AOI, resources first); never mark a phase COMPLETED without evidence in the verification table.
Output: results tables with real output, defects found/fixed, deployment instructions, final validation report, updated statuses.
MANDATORY DOCS CLOSE-OUT (the phase is NOT finished until done; follow .claude/rules/documentation.md). Update in this order, with real test output, dates and counts, never expected results: (1) docs/project/PROJECT_STATUS.md (phase status label + evidence, components, test results, known bugs); (2) docs/project/NEXT_STEPS.md; (3) docs/project/TASK_LOG.md; (4) CHANGELOG.md; (5) docs/phases/PHASE_NN.md (completion evidence, limitations, verification table); (6) docs/architecture/* and docs/scientific/* if design or science changed; (7) docs/adr/ for new decisions; (8) docs/project/PROJECT_MEMORY.md for durable lessons; (9) docs/project/ROADMAP.md only if scope changed as authorized. Fix contradictions between docs. Do not mark COMPLETED without evidence. End your report with a list of every doc file updated.
```


---

# PARALLEL ML DEVELOPMENT TRACK (M0 to M9)

This track builds the landslide early-prediction ML models **outside** the 10 roadmap phases. The user explicitly authorized it on 2026-11-15 (this is the "separately authorized ML stage" of ADR-0002). It does **not** change the 10 phases: Phases 6-10 continue exactly as written, without ML. Nothing from this track is wired into the backend, frontend, API or database. `PREDICTION_BACKEND` stays `none`; the model-slot handoff (`models/<model_id>/<version>/`) happens later, only when the user decides.

## Track rules (embedded in every M-prompt)

- **Location:** all new ML code, notebooks, configs, reports and experiment outputs live under `precursor-ai/ml/` (data under `data/ml/`). Existing backend code (Phase 2 acquisition, Phase 3 InSAR, Phase 4 environmental, Phase 5 `features_cv`) may be **imported and reused read-only**; do not modify it. If a bug is found there, report it; fix only with my approval and a regression test.
- **Real data only for performance claims.** Synthetic data may be used only for pipeline smoke tests, always labelled; a model trained or scored on synthetic data is never reported as a result.
- **No downloads or Earthdata login without my approval** of specific files (name, source, size, AOI, total GB, disk/time). Never print credentials. Large-data steps stop and ask first.
- **Scientific integrity:** every metric is on held-out data (spatial-block CV and a temporal hold-out where dates exist); never report training or validation-fold-tuned scores as performance; report negative and weak results honestly; document the inventory-bias caveat (catalogs are incomplete and biased to reported, accessible places); absence of a landslide record is NOT proof of stability (use "background", not "negative"). Landslide labels must be temporally compatible with the satellite data used (see M1).
- **No leakage:** spatial buffers, temporal cut-offs, no future information in features, no random pixel splits.
- **Reproducibility:** fixed seeds, pinned dependency versions, dataset hashes, code version and config logged for every run; one command re-runs each stage.
- **Dependencies:** list and justify every new package before installing; keep the ML environment separate from the backend image (own `ml/requirements.txt` or env) so Docker backend/frontend are not affected.
- **Docs:** each stage ends with a report in `ml/reports/` and updates `docs/ml/ML_STATUS.md` (created in M0), `docs/project/TASK_LOG.md` and `CHANGELOG.md`; `PROJECT_STATUS.md` gets one separate "ML track" line, never changing roadmap phase statuses. Record real outputs only; unverified = `NOT_VERIFIED`.
- **Stop points:** M1 (dataset approval), M5 (EDA review), M7 (compute/model-family approval) and M9 (handoff) wait for my explicit answer. Do not start the next M-stage on your own.
- Each stage's report ends with: what was done, real results, what was not verified, risks, and the decision needed from me.

---

## Literature-informed model guidance (web research, 2026-11-15; abstracts/snippets only, full papers NOT read)

No single model wins across studies; results depend on area, factors and evaluation. Use this to set priorities, then let M5/M7 evidence decide. M1 must re-verify and extend this reading list (fetch full texts, record DOIs in `docs/ml/DATASET_LOG.md` or `ml/reports/M1_literature.md`).

| Finding | Implication for the track | Source |
|---|---|---|
| Tabular conditioning factors: Random Forest, XGBoost, LightGBM usually strong; RF best of 10 models in a Nepal study (test AUC 0.928, XGB 0.881, LGBM 0.844), beating deep models there | Tabular baselines (RF + gradient boosting) are the default susceptibility models | [Springer 2026](https://link.springer.com/article/10.1007/s44475-026-00029-0) |
| CNN/hybrid deep models beat RF/LR/SVM in some studies (Wenchuan; CNN-LSTM in a factor-selection study) but not consistently | Try a patch CNN only if M5 shows enough real positives and spatial structure to justify it; always compare to tabular | [MDPI Remote Sens. 2022](https://mdpi.com/2072-4292/14/2/321), [arXiv 2309.06062](https://arxiv.org/pdf/2309.06062) |
| Review of ML for susceptibility mapping | Use as the survey baseline for factor lists and metrics | [Remote Sens. 2022 survey](https://doi.org/10.3390/rs14133029) |
| Deformation/trigger prediction: LSTM/GRU/TCN on InSAR (or GB-InSAR) series, often with rainfall; WT-LSTM RMSE 1.16-2.19 mm on a site; MUSEnet fuses daily rainfall/water level with InSAR sequences | Trigger-task candidates: GBM on windowed features first, then LSTM/TCN if enough long series exist. Site-specific results do not transfer | [MDPI RS 17(11)](https://mdpi-res.com/d_attachment/remotesensing/remotesensing-17-01893/article_deploy/remotesensing-17-01893.pdf), [DOAJ JSTARS 2024](https://doaj.org/article/beb898178d984eefbd7c93ecaeefe1a6) |
| Rainfall-triggered occurrence: LSTM-TCN probability combined with an effective-rainfall threshold curve (Wanzhou) | Rainfall-threshold curve is a baseline and an evaluation comparator, inside `ml/` only | [DOAJ 2024](https://doaj.org/article/3cc95dff70c44700a6094ddf52004de1) |
| SBAS-InSAR + DNN/XGB/RF/LightGBM under extreme rainfall: distance to river, cumulative rainfall and TWI were most influential; GBDT strongest under extreme rainfall | Include TWI, distance-to-river and cumulative rainfall features | [DOAJ 2022](https://doaj.org/article/e4c2ced6584542d09063cc811e138813) |
| Random cross-validation gives inflated scores; spatial block (small-block nested) CV is a realistic compromise | Spatial-block nested CV is mandatory (already a Track rule) | [EGUsphere 2026-579](https://egusphere.copernicus.org/preprints/2026/egusphere-2026-579/egusphere-2026-579.pdf) |
| Random "stable" samples can fall on unstable terrain; physically or rule-informed sampling improved AUC (+16.46% random CV, +29% spatial CV in one paper) | Background sampling must be careful and documented; test sensitivity to sampling strategy in M8 | [MDPI IJGI 14(9)](https://www.mdpi.com/2220-9964/14/9/339), [MDPI RS 18(408)](https://mdpi-res.com/d_attachment/remotesensing/remotesensing-18-00408/article_deploy/remotesensing-18-00408.pdf) |
| COOLR extends the Global Landslide Catalog with citizen reports and event inventories (22 rainfall-triggered inventories added); data on Figshare and the NASA Landslide Viewer | Primary candidate label sources for M1 besides GLC | [PMC COOLR](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6608936/), [NTRS 2025](https://ntrs.nasa.gov/citations/20250007585), [NASA COOLR](https://gpm.nasa.gov/applications/landslides/coolr) |
| NISAR: search found no data-start date; a March 2025 NASA Q&A says L-band change detection was still planned | NISAR temporal depth is UNVERIFIED; M1 must check the real catalog | [NASA Applied Sciences Q&A](https://appliedsciences.nasa.gov/sites/default/files/2025-03/Part%202%20Landslide%202025%20Q%26A%20Session.docx.pdf) |

**Working hypothesis to test (not a conclusion):** susceptibility: RF / XGBoost / LightGBM on harmonized conditioning factors (strong baselines, small data friendly, SHAP-explainable); trigger: gradient boosting on windowed rainfall + soil-moisture + InSAR features first, deep temporal models (LSTM/TCN) only if long real series exist. Expect that InSAR may help mostly for slow-moving landslides, and rainfall/terrain dominate rainfall-triggered failures.

## M0: ML track governance and workspace

```text
You are working on PRECURSOR AI (precursor-ai/). I authorize a SEPARATE ML development track (M0-M9) for landslide early prediction, outside the 10 roadmap phases. This is M0.

Session start: read CLAUDE.md, docs/project/PROJECT_STATUS.md, NEXT_STEPS.md, ADR-0002, ADR-0008, .claude/rules/scientific-integrity.md, Prompts.md (section "PARALLEL ML DEVELOPMENT TRACK", including the Track rules).

Do:
1. Record the authorization: write ADR-0009 "ML development track authorized, isolated from the 10 phases" (date 2026-11-15, user decision): ML work only under ml/ and data/ml/; no wiring into backend/frontend/API/DB; PREDICTION_BACKEND stays none; handoff via the ADR-0008 ML slot only on my later decision; the 10 phases stay ML-free; real-data-only performance claims. Update ADR index. Do not edit ADR-0002 or ADR-0008 decisions (add a "see ADR-0009" pointer only).
2. Make the minimal, scoped rule edits so agents are not blocked: CLAUDE.md and .claude/rules/scientific-integrity.md get one short paragraph each: "ML development is permitted ONLY inside the ML track (ml/, ADR-0009); every other directory and every roadmap phase remains ML-free". Do not weaken any other rule. Add .claude/rules/ml.md (paths: ml/**) with the Track rules above.
3. Create the workspace skeleton (no model code yet): ml/README.md; ml/configs/; ml/src/precursor_ml/ (package stub); ml/notebooks/; ml/reports/; ml/tests/; data/ml/{raw,interim,processed,splits}/ (gitignored, with READMEs); docs/ml/ML_STATUS.md (stage table M0-M9, all NOT_STARTED except M0), docs/ml/DATASET_LOG.md (source, licence, version, date, size, checksum, approval), docs/ml/EXPERIMENT_LOG.md.
4. Environment: propose (do not install yet) the ML dependency list with one-line justifications (e.g. numpy, pandas, scipy, scikit-learn, xgboost, lightgbm, shap, matplotlib, seaborn, geopandas, rasterio, pyarrow, optuna; PyTorch only if M7 justifies deep models; experiment tracking: plain files vs MLflow). Ask me to approve the list. Check what is already installed in backend/.venv and whether GPU exists (report, do not assume).
5. Define the experiment-tracking convention: run id, config hash, seed, dataset hash, code version, metrics file, artifacts folder.
6. Tests: a smoke test of the package import, a test that ml/ does not import from app.api or write to the DB, and a guard test that no file outside ml/ and data/ml/ was touched by the ML track (script, documented).

Constraints: no model code, no downloads, no training, no changes to roadmap phase statuses.
Stop after M0 and wait for my approval of the dependency list.
DOCS: update ML_STATUS, TASK_LOG, CHANGELOG, ADR index, one ML line in PROJECT_STATUS. List every doc updated.
```

---

## M1: Problem definition, dataset discovery and feasibility (STOP for approval)

```text
You are working on the PRECURSOR AI ML track, stage M1. Apply the Track rules from Prompts.md. Prerequisite: M0 done.

GOAL: define exactly what the models predict and find out, with evidence, which datasets can really support it. The user wants datasets brought from the NISAR API. Test whether that is feasible BEFORE any download.

Session start: read the "Literature-informed model guidance" section in Prompts.md (then verify it against the full papers, write ml/reports/M1_literature.md with DOI, data, metrics, validation method and limits for at least 10 relevant papers incl. NISAR/L-band landslide work), ml/README.md, docs/ml/ML_STATUS.md, ADR-0009, docs/nasa-data-sources.md, docs/phase-2-data-acquisition.md, docs/scientific/ENVIRONMENTAL_DATA_SOURCES.md, docs/scientific/INSAR_METHODOLOGY.md, docs/phases/PHASE_02.md and PHASE_03.md.

Do:
1. PROBLEM DEFINITION (write ml/reports/M1_problem_definition.md): two tasks. (a) SUSCEPTIBILITY: static, per cell, "where are slopes prone to fail"; binary target (landslide event occurred in the cell during the study window vs background). (b) TRIGGER / EARLY WARNING: dynamic, per cell and time step, "will a landslide occur within H days"; define time step, horizon H, lead times, spatial unit. Define label construction, label noise, the metrics for rare events (PR-AUC, recall at fixed false-alarm rate, Brier, calibration), splits (spatial-block CV + temporal hold-out), and baselines (prior, rainfall-threshold, logistic regression). State what each task needs from data.
2. DATA FEASIBILITY (write ml/reports/M1_feasibility.md) using real catalog queries only (anonymous CMR/ASF search via the existing Phase 2 services, no login, no download):
   - NISAR: which products exist (GUNW, GCOV, GSLC, GOFF), real date range, real geographic coverage, revisit, how many acquisitions per candidate region, typical file size. Report what the catalog actually returns; do not assume. NISAR started returning data recently, so check the real temporal depth.
   - TEMPORAL COMPATIBILITY CHECK (critical): compare the NISAR date range with every candidate landslide label source (NASA Global Landslide Catalog is a one-time export current to 2016-03-07; check NASA COOLR / updated catalogs, national and regional inventories, USGS landslide inventories, news-derived inventories, Copernicus/EMS, any open inventory with dates in the NISAR period). If labelled events do not overlap NISAR in time, say so clearly and state the consequences.
   - Alternatives that give long history: Sentinel-1 (ASF, 2014+), ALOS-2, Copernicus EGMS ground-motion products (Europe), NASA OPERA DISP/ products (check availability), plus the non-SAR factors: NASADEM/Copernicus GLO-30, GPM IMERG, SMAP, SoilGrids, ESA WorldCover, lithology/geology, USGS earthquakes.
   - For each candidate dataset: source URL, licence, access method, variables, resolution, date range, coverage, per-file and total size, role (feature | label | both), maturity, known issues. Mark every unverified claim NOT_VERIFIED.
3. PROPOSE 2-3 candidate study designs ranked, for example: (A) NISAR-only trigger model (probably infeasible if labels do not overlap); (B) multi-source susceptibility model with long-history labels and static + rainfall factors, InSAR from Sentinel-1/NISAR as an auxiliary where available; (C) hybrid. For each: target region(s) (any AOI, not hardcoded), expected number of positive events, class balance, total download size, disk, compute, time, risks, and your recommendation with reasoning.
4. Present a DOWNLOAD PROPOSAL for the recommended design: exact dataset names, file counts, sizes, AOI bbox, date range, total GB, disk and time estimate. Do NOT download anything.

STOP. Wait for my explicit approval of the study design, region(s) and download list. Update docs/ml/DATASET_LOG.md with candidates (status PROPOSED), ML_STATUS, TASK_LOG, CHANGELOG. List every doc updated.
```

---

## M2: Data acquisition (approved files only)

```text
You are working on the PRECURSOR AI ML track, stage M2. Apply the Track rules. Prerequisite: M1 approved by me in writing (study design, regions, exact file list).

Session start: read ml/reports/M1_*.md, docs/ml/DATASET_LOG.md, docs/earthdata-authentication.md, docs/phase-2-data-acquisition.md.

Do:
1. Acquire ONLY the approved list, reusing the Phase 2 pipeline (CLI/services: discover, register, download, validate). Credentials come from .env; never print them. Download in batches with resumable jobs, retries and disk checks; stop on any unexpected size growth.
2. Non-Earthdata sources (inventories, SoilGrids, WorldCover, geology, USGS): fetch only the approved items; record URL, licence, retrieval date, checksum.
3. For each file: size, SHA-256, file validation (integrity only; VALIDATED is not scientific validation), and an entry in docs/ml/DATASET_LOG.md. Data goes to data/ml/raw/ (or reuse data/raw/ via manifest pointers, no duplicates).
4. Produce ml/reports/M2_acquisition.md: what arrived, what failed, what is missing vs the approved list, real totals. Do not silently substitute missing files.
5. Tests: manifest completeness check, checksum verification, idempotent re-run.

Constraints: no preprocessing, no modelling. If a file is larger than approved or auth fails, stop and ask.
DOCS: ML_STATUS, DATASET_LOG, TASK_LOG, CHANGELOG, one ML line in PROJECT_STATUS. List every doc updated.
```

---

## M3: Preprocessing and harmonization

```text
You are working on the PRECURSOR AI ML track, stage M3. Apply the Track rules. Prerequisite: M2 complete.

Session start: read ml/reports/M2_acquisition.md, docs/ml/DATASET_LOG.md, docs/scientific/{INSAR_METHODOLOGY,TERRAIN_METHODOLOGY,RAINFALL_METHODOLOGY,FEATURE_EXTRACTION}.md, ADR-0006 (stack manifest and reference grid) and ADR-0007. Reuse existing, read-only: services/insar (inspection, adapters, displacement, coherence, velocity), services/environmental (raster io, alignment, reference_grid, DEM terrain, rainfall, soil, land cover), services/features_cv.

Do:
1. SAR/InSAR products: inspect real files first (record the real HDF5 layout, units, dataset names, identification fields; this also verifies the Phase 3 adapter assumptions: report mismatches, do not patch Phase 3). Derive LOS displacement, coherence, velocity where scientifically justified. Keep the sign-convention caveat. LOS is not vertical; no risk language.
2. Common reference grid per study region (metric CRS chosen from the AOI, documented), align all rasters (bilinear for continuous, nearest for categorical), clip, handle nodata (NaN, never zero), record resampling per layer.
3. Static factors: elevation, slope, aspect, curvature, TWI/flow accumulation (only if justified), land cover, soil, lithology, distance to rivers/faults/roads, NDVI.
4. Dynamic factors: rainfall (accumulations over 1/3/7/14/30 days, antecedent indices, max intensity), soil moisture, InSAR time series windows. Time-index everything to UTC; align to the study time step.
5. Labels: build event geometries and dates from the approved inventory, with location-accuracy radius.
6. Persist interim products to data/ml/interim/ with a manifest (source hashes, parameters, code version, seed).
7. Tests on real-data samples (small window) and labelled synthetic fixtures; idempotent re-run; CRS/transform preservation; nodata propagation.

Constraints: no modelling, no feature selection yet. Document every processing choice and its scientific justification in ml/reports/M3_preprocessing.md. REAL_DATA_VALIDATION for Phase 3 adapters: report PERFORMED / PARTIAL honestly.
DOCS: ML_STATUS, DATASET_LOG, TASK_LOG, CHANGELOG, ML line in PROJECT_STATUS; if adapter mismatches were found, add them to PROJECT_STATUS known issues (report only). List every doc updated.
```

---

## M4: Data cleaning and quality control

```text
You are working on the PRECURSOR AI ML track, stage M4. Apply the Track rules. Prerequisite: M3 complete.

Session start: read ml/reports/M3_preprocessing.md, docs/ml/DATASET_LOG.md.

Do:
1. LABEL CLEANING: duplicate events, same event reported twice, wrong coordinates (ocean, outside AOI, impossible slopes), date problems (MM/DD vs DD/MM, missing dates, future dates), unknown/low location accuracy (exclude from strict set, keep in an "excluded" list with reason), event types that are not landslides, triggers (rainfall, earthquake, human).
2. FEATURE CLEANING: nodata/fill values, sensor artifacts, unwrapping errors, low-coherence masking (documented thresholds as quality masks, not risk), outliers (flag, do not blindly delete; justify), unit checks, physical range checks (slope 0-90, rainfall >= 0, etc.).
3. MISSING DATA: quantify per feature and per region/time; decide per feature: keep NaN with model-native handling, drop, or impute. Imputation only with a documented method fitted on the TRAIN split only (no leakage); never impute labels.
4. BACKGROUND SAMPLING: define background points (outside buffer of 2x location-accuracy radius, same region, stratified by terrain, seeded); record ratio and the pseudo-absence caveat.
5. LEAKAGE AUDIT: write and run automated checks (spatial proximity across splits, temporal order, features using future data, duplicated rows, target-derived features); report pass/fail.
6. Produce the cleaned dataset in data/ml/processed/ (versioned, hashed) with a cleaning log (rows removed/flagged and why) and ml/reports/M4_cleaning.md.
7. Tests for each cleaning rule and the leakage checks.

Constraints: no modelling, no tuning. Every rule is documented and reversible (raw is never overwritten).
DOCS: ML_STATUS, DATASET_LOG, TASK_LOG, CHANGELOG. List every doc updated.
```

---

## M5: Exploratory data analysis (STOP for review)

```text
You are working on the PRECURSOR AI ML track, stage M5. Apply the Track rules. Prerequisite: M4 complete.

Session start: read ml/reports/M4_cleaning.md and the cleaned dataset manifest. Use the data-analysis-jupyter, pandas-best-practices and dataviz skills as needed.

Do (notebooks in ml/notebooks/, figures and report in ml/reports/M5_eda.md; use ONLY the training portion for any decision, the test/hold-out is not inspected for modelling choices):
1. Dataset overview: sizes, class balance, positives per region/year, coverage maps, temporal coverage, missingness patterns.
2. Univariate and bivariate analysis: each feature vs label (distributions by class, effect sizes, KS/Mann-Whitney with multiple-testing caution), slope/rainfall/soil/land-cover/lithology relationships, InSAR velocity and coherence vs events.
3. Spatial analysis: spatial autocorrelation (Moran's I), clustering of events, reporting bias (distance to roads/cities vs event density), region imbalance.
4. Temporal analysis: seasonality, rainfall-event relationships, lead-time relationships for the trigger task, trend and non-stationarity.
5. Multicollinearity (VIF, correlation clusters), feature redundancy, sensor/geometry effects.
6. Sanity checks against physical expectations (steeper slopes, heavier antecedent rain, etc.) and flag anything surprising as possible leakage or artifact.
7. Data sufficiency: is the number of real positives enough for the planned model families? Learning-curve style estimates, minimum-event requirements. Be blunt if data is too small.
8. Recommendation: which tasks (susceptibility, trigger) are feasible with this data, which model families are justified (and which are not), which features to keep, and the risks.

Constraints: no model fitting except trivial diagnostic fits (e.g. univariate), none reported as performance. No test-set peeking.
STOP. Present findings and wait for my decision on tasks, model families and compute budget.
DOCS: ML_STATUS, TASK_LOG, CHANGELOG. List every doc updated.
```

---

## M6: Feature engineering, selection and final splits

```text
You are working on the PRECURSOR AI ML track, stage M6. Apply the Track rules. Prerequisite: M5 reviewed and approved by me.

Session start: read ml/reports/M5_eda.md and my decisions, docs/scientific/FEATURE_EXTRACTION.md, docs/scientific/LABELLED_DATASET.md, services/features_cv/schema.py (ModelInputSpec).

Do:
1. Engineer only features justified by the EDA and by physical reasoning (e.g. terrain derivatives, rainfall accumulation/intensity/antecedent indices, soil moisture, vegetation, lithology classes, distance layers, InSAR velocity/coherence statistics, velocity change), reusing Phase 5 extractors where they fit. Versioned feature schema; units, source, window, lineage per feature.
2. Categorical handling (lithology, land cover): document encoding; no encoding that leaks the target.
3. Feature selection on the TRAIN split only (collinearity pruning, permutation importance, stability across spatial folds). Keep a full-feature variant and a reduced variant for comparison.
4. FINAL SPLITS: spatial-block cross-validation folds with a buffer gap; a temporal hold-out (train before cut-off date, test after) for the trigger task; a spatial hold-out region if multiple regions exist. Persist split indices with a hash; automated leakage tests must pass.
5. Export model-ready datasets (Parquet/NumPy) in data/ml/splits/ with manifests, plus a ModelInputSpec for each variant, built with the existing class (do not redefine), so a later model can be validated against the same contract.
6. Tests: determinism, no leakage, schema validation, no score-like feature names.

Constraints: no model training yet. ml/reports/M6_features_splits.md with the feature list, drop reasons and split design.
DOCS: ML_STATUS, DATASET_LOG, TASK_LOG, CHANGELOG. List every doc updated.
```

---

## M7: Baselines and model training (STOP for compute/model-family approval)

```text
You are working on the PRECURSOR AI ML track, stage M7. Apply the Track rules. Prerequisite: M6 complete and my approval of tasks, model families and compute budget.

Session start: read ml/reports/M1_literature.md, M5_eda.md, M6_features_splits.md, docs/ml/EXPERIMENT_LOG.md, ml/README.md. Prior literature (Prompts.md guidance section) suggests RF/XGBoost/LightGBM as strong tabular baselines; deep models only on evidence.

Do:
1. BASELINES FIRST (mandatory, same splits and metrics as every model): (a) class-prior, (b) simple rainfall-threshold rule used ONLY as an evaluation baseline inside ml/ (never in the product), (c) logistic regression with sensible regularisation. Every later model must be compared to these.
2. MODEL FAMILIES (only those justified by M5 and approved by me): Random Forest; XGBoost; LightGBM; and, only if the data volume and spatial/temporal structure justify it and I approve the dependency, a CNN on raster patches (susceptibility) and a temporal model (TCN/LSTM/GRU or gradient boosting on windowed features) for the trigger task over InSAR/rainfall series. State the data-size justification for each deep model; do not train deep models on a handful of events.
3. TRAINING PROTOCOL: nested spatial-block CV for hyperparameter search (Optuna or grid; budget stated), class-imbalance handling (class weights, balanced subsampling, focal loss for deep models) chosen on CV only, early stopping on validation folds, fixed seeds, 3+ seeds for variance, no tuning on the hold-out. Track every run (config, seed, dataset hash, code version, metrics, runtime, hardware) per the experiment convention.
4. Save artifacts per run in ml/runs/<run_id>/ (model file, config, metrics, feature spec, split hash). Do not copy anything to models/ yet.
5. Tests: training is reproducible within tolerance for a fixed seed; CV never mixes buffered neighbours; a run refuses data whose hash differs from the config.

Constraints: no peeking at the final hold-out until the model choice is frozen; do not report tuned CV scores as final performance. If the data is too small for a family, say so and skip it with a reason.
Output: ml/reports/M7_training.md with the experiment table (all runs, including failures), compute used, and the frozen candidate list.
DOCS: ML_STATUS, EXPERIMENT_LOG, TASK_LOG, CHANGELOG. List every doc updated. STOP before M8 and wait for my OK on the frozen candidates.
```

---

## M8: Evaluation, calibration, uncertainty and explainability

```text
You are working on the PRECURSOR AI ML track, stage M8. Apply the Track rules. Prerequisite: M7 candidates frozen and approved by me.

Session start: read ml/reports/M7_training.md, docs/ml/EXPERIMENT_LOG.md.

Do:
1. FINAL EVALUATION, once, on the untouched hold-outs (temporal hold-out and spatial hold-out region): PR-AUC, ROC-AUC (secondary), recall at fixed false-alarm rate, precision at fixed recall, F-beta, Brier score, log loss, calibration curve and ECE; for the trigger task also hit rate, false-alarm rate, false alarms per area per year and lead-time analysis. Bootstrap confidence intervals (block bootstrap over space/time). Compare every model to the baselines with a significance caveat.
2. CALIBRATION: Platt/isotonic fitted on a calibration split separate from the test set; report before/after. Do not call outputs probabilities unless calibrated on independent data.
3. UNCERTAINTY: ensemble variance or conformal prediction (justify), prediction intervals or abstain-region; coverage check on the hold-out.
4. EXPLAINABILITY (a real model exists now): SHAP (TreeExplainer for tree models), permutation importance, partial dependence; stability across folds; check that explanations are physically plausible and flag spurious features (e.g. distance to roads as a reporting-bias proxy). Explanations are not causality.
5. ROBUSTNESS AND FAILURE ANALYSIS: performance by region, terrain class, land cover, rainfall regime, event size, location-accuracy class; sensitivity to label noise and to the background sampling ratio; ablations (without InSAR, without rainfall, static-only) to show what each source adds; out-of-region generalization.
6. HONEST CONCLUSION: whether the models beat the baselines meaningfully, whether they are usable for any purpose, and the conditions under which they must not be used.
7. Tests: metric implementations against hand-computed cases; evaluation script refuses to run on training data as "test".

Constraints: no re-tuning after seeing hold-out results; if results are poor, report them as they are. Never label results as an operational warning capability.
Output: ml/reports/M8_evaluation.md with tables, figures, CIs, and a limitations section.
DOCS: ML_STATUS, EXPERIMENT_LOG, TASK_LOG, CHANGELOG, docs/scientific/SCIENTIFIC_LIMITATIONS.md (ML subsection). List every doc updated.
```

---

## M9: Packaging, model card and handoff (STOP; integration is a separate decision)

```text
You are working on the PRECURSOR AI ML track, stage M9. Apply the Track rules. Prerequisite: M8 complete and reviewed by me.

Session start: read ml/reports/M8_evaluation.md, docs/phases/PHASE_07.md (if Phase 7 exists in code, also backend/app/services/prediction/), ADR-0008, docs/architecture/ML_INTEGRATION.md if present.

Do:
1. For each model I choose to keep, create the artifact package at ml/export/<model_id>/<version>/ laid out exactly as the ADR-0008 ML slot expects (it will be copied to models/<model_id>/<version>/ only later, by my decision): model file(s), metadata.json, model_card.md, feature spec built with the existing ModelInputSpec, training_data_provenance.json (datasets, versions, licences, hashes, date ranges, regions), calibration artifacts, explainer config and background-dataset reference, valid region and valid time window, known failure modes, intended and non-intended use, evaluation summary with CIs, code version and seed.
2. Write a standalone, tested inference function inside ml/ that loads the package, validates the input against ModelInputSpec, and refuses out-of-region/out-of-time/low-quality inputs. It stays inside ml/; do not register it in the backend.
3. Check compatibility with the ML slot contract (Predictor/ModelRegistry from Phase 7 if built; otherwise with the documented contract): list gaps and what Phase 7 would need. Do not modify Phase 7.
4. Final ML report ml/reports/M9_final.md: data used, methods, results, limitations, biases, reproducibility instructions (one command per stage), and the clearly stated intended use: research prototype, not an operational warning system.
5. Reproducibility test: rebuild a package from the logged config and verify metrics match within tolerance.

Constraints: no integration into backend/frontend/DB; PREDICTION_BACKEND stays none; no mock-to-real switch. Integration is a separate step that needs my explicit instruction and will update Phase 7/9.
DOCS: ML_STATUS, TASK_LOG, CHANGELOG, docs/ml/*, ML line in PROJECT_STATUS; docs/architecture/ML_INTEGRATION.md gets a "first candidate model" gap list only if that file exists. List every doc updated.
```
