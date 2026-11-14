# ADR-0007: Feature extraction, labelled sample dataset and the dependencies behind them

- Status: ACCEPTED
- Date: 2026-11-14 (Phase 5, user decisions of the same day)

## Context
Phase 5 turns the Phase 4 aligned stack into reusable per-pixel feature rasters and into a leakage-safe table of landslide-event and background samples for a FUTURE model. No model is trained or run ([ADR-0002](ADR-0002-ml-deferral.md)). The repository holds no real data, so everything is verified on labelled synthetic fixtures.

## Decision
1. **Placement.** `backend/app/services/features_cv/` (same reasoning as [ADR-0004](ADR-0004-insar-placement-and-strategy.md) and [ADR-0005](ADR-0005-environmental-integration-design.md): reuse the Phase 4 raster code, config and layering). `ai_engine/*` stays README-only. Inputs: the Phase 4 `manifest.json` and the aligned rasters it names. No second AOI or download system.
2. **Dependencies (supersedes the scipy rejection in ADR-0005).** Approved and pinned in `requirements.txt`: `scikit-image` (GLCM texture), `scipy` (`ndimage` filters), `pyarrow` (Parquet export). ADR-0005 rejected scipy because Phase 4 needed none of it (a distance transform was replaced by shapely). That changed: Phase 5 needs focal filters (local relief, roughness), Gaussian smoothing for curvature, Sobel/edge operators for lineament and slope-break features, and `cKDTree` for sample spacing and leakage checks, and re-implementing these in numpy would be longer and less tested. NOT approved: `opencv-python-headless` (scikit-image + scipy cover the need; revisit only with a written justification) and `torch` (never installed; a PyTorch `Dataset` interface exists behind a lazy optional import and is never run).
3. **Persistence: files plus manifest, no database table, no migration.** Features under `data/processed/features/<area_id>/`, datasets under `data/processed/datasets/<area_id>/`, each with a `manifest.json` carrying `schema_version`, the source (Phase 4) manifest hash, parameters, seed, code version and a synthetic flag. Entry point is a CLI/service; the API is read-only (feature manifest, dataset summary).
4. **Versioning.** `FEATURE_SCHEMA_VERSION` (semantic: a new feature is MINOR, a changed definition/unit/name is MAJOR), `DATASET_SCHEMA_VERSION` and a `CODE_VERSION` string are written into every manifest. `ModelInputSpec` names the features, their schema version and the grid contract; Phase 7's model registry validates a model's spec against it (the ML SLOT, see Prompts.md header). Phase 5 provides only the schema; it does not implement `services/prediction/`.
5. **Features are descriptive.** Terrain (local relief, roughness, curvature, edge/lineament density, GLCM texture, slope-break) and change features. Window sizes are parameters stated in pixels and metres. Edge-density cut-offs are parameters of an edge detector, not hazard thresholds. Change features (NDVI difference, coherence change, InSAR velocity gradient) are refused unless two DATED inputs of REAL origin on the same grid exist; Phase 4 stores one layer per type, so the pipeline reports them NOT_AVAILABLE.
6. **Dataset design.**
   * Events whose date, coordinates or `location_accuracy` are unusable are EXCLUDED and listed with a reason. `location_accuracy` is read from `original_attributes` (no model column, no migration) and mapped to a radius in metres by a documented lookup; the parsing rules are NOT_VERIFIED against a real file.
   * Unlabelled samples are called **BACKGROUND**, never "negatives": the catalog is incomplete and biased toward reported, accessible, populated places, so unlabelled is not proven stable. Background points lie in the same AOI, outside `max(2 x accuracy radius, minimum buffer)` of every event (metric CRS), only on valid pixels, stratified by terrain bins, with a recorded seed and ratio. One strategy is implemented (stratified); random background is documented as an alternative only.
   * Splits: spatial-block (block size in metres, whole blocks per split, a gap in metres between train and test) and temporal (cut-off date). A leakage checker proves no train/test pair within the gap, no block shared, no train event after the cut-off. All seeded and deterministic.
   * Per-point dynamic features are deferred to Phase 6: the dynamic columns are reserved and `NOT_AVAILABLE` with a reason, together with `event_date` and the lead-time anchors (t-1, t-3, t-7, t-14, t-30 days). No AOI-mean proxy values are written.
7. **ML boundary.** No training, inference, scoring, model artifact, or risk/susceptibility label or class. A test scans every output schema and field name for score-like terms.

## Alternatives considered
OpenCV for filtering (rejected: duplicates scikit-image/scipy). A database table for samples (rejected by the user: files plus manifest match Phase 4). AOI-mean dynamic values per sample (rejected: they would look like point observations). Calling background points "negatives" (rejected: scientifically wrong for an incomplete catalog). Placing code in `ai_engine/` (rejected: it must not import FastAPI/DB and would duplicate the raster layer).

## Consequences
Three new runtime dependencies and a larger Docker image (size recorded in the changelog). Features and samples are reproducible and inspectable on disk. Nothing here is validated on real data; the dataset is only as good as the catalog, which is incomplete and reporting-biased.

## Related
[PHASE_05](../phases/PHASE_05.md), [FEATURE_EXTRACTION](../scientific/FEATURE_EXTRACTION.md), [LABELLED_DATASET](../scientific/LABELLED_DATASET.md), [ADR-0006](ADR-0006-stack-manifest-and-reference-grid.md)
