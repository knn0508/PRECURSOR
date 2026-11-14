# Phase 5: Computer Vision & Feature Extraction (+ labelled dataset)

Status: **PARTIALLY_COMPLETED**: implemented and tested on **synthetic** data only (2026-11-14). **`REAL_DATA_VALIDATION: NOT_PERFORMED`**: no real raster, catalog or InSAR product has been processed. No ML of any kind. Roadmap: [ROADMAP](../project/ROADMAP.md). Decision record: [ADR-0007](../adr/ADR-0007-feature-extraction-and-labelled-dataset.md).

## Objective and scope
A reusable, AOI-generic feature-extraction pipeline over the Phase 4 aligned stack, and a LEAKAGE-SAFE labelled sample dataset (landslide-event and background samples) as a data product for a FUTURE model. Scope authorized by the user on 2026-11-14 (labelled dataset added to the original "feature extraction; CV interfaces" scope). **Out of scope:** training, fine-tuning, inference, scoring, model artifacts, risk/susceptibility labels or classes, per-point dynamic features (Phase 6), optical imagery (interface only), a frontend page, a database table or migration.

## Prerequisites
Phase 4 at least PARTIALLY_COMPLETED with a stack manifest and an aligned reference grid (met on synthetic data; the loader returns NOT_AVAILABLE otherwise). Phase 2 landslide table for real events (empty in the dev database).

## What exists
Code `backend/app/services/features_cv/`:
- `tiling.py` windows/halo, `tiled_apply`, windowed reads, grid-equality guard, recorded normalisation.
- `terrain.py`, `texture.py`, `change.py`: pure feature functions ([FEATURE_EXTRACTION](../scientific/FEATURE_EXTRACTION.md)); change features refuse anything but two dated REAL inputs.
- `registry.py` (`FeatureExtractor` protocol, `FeatureRegistry`, terrain/texture/change extractors), `schema.py` (`ModelInputSpec`), `types.py` (schema/code versions, forbidden score-like name tokens).
- `stack.py` (reads the Phase 4 `manifest.json` and aligned rasters by file name only), `pipeline.py` (feature COGs + manifest), `dataset.py` / `dataset_run.py` / `events.py` (labelled dataset, [LABELLED_DATASET](../scientific/LABELLED_DATASET.md)), `export.py` (COG, Parquet, NumPy, lazy PyTorch interface), `__main__.py` (CLI).
- API `backend/app/api/v1/features_cv.py`: three GET routes under `/api/v1/features-cv` ([API_DOCUMENTATION](../architecture/API_DOCUMENTATION.md)).
- Outputs: `data/processed/features/<area_id>/` and `data/processed/datasets/<area_id>/`, each with a `manifest.json` (schema version, code version, SHA-256 of the source manifest, parameters, seed, synthetic flag).

## Feature status (honest)
| Item | Status | Notes |
|---|---|---|
| local relief, TRI, Laplacian curvature, slope break, lineament density | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | analytic oracles pass; parameters untuned |
| GLCM texture (6 properties, SLOPE and NDVI) | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | block grid, declared; checkerboard oracle |
| NDVI difference, coherence change, velocity gradient | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | guard tested; NOT_AVAILABLE in practice (one layer per type in the stack) |
| Optical imagery features | NOT_STARTED (interface only) | no source approved |
| Labelled dataset (EVENT + BACKGROUND, splits, leakage check) | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | synthetic events only; `location_accuracy` parsing NOT_VERIFIED |
| Per-point dynamic features | NOT_AVAILABLE (deferred to Phase 6) | columns reserved, all null |
| `ModelInputSpec` (ML SLOT feature contract) | IMPLEMENTED | schema + compatibility check only; no `services/prediction/` (Phase 7) |
| PyTorch `Dataset` interface | INTERFACE_ONLY | lazy import, torch not installed, never run |

## Acceptance vs evidence
Met on synthetic data: determinism (identical array hashes on rerun), CRS/transform preservation, nodata propagation (NaN, never zero), schema validation, leakage proofs (each check also shown to fire on a corrupted table), empty/tiny AOI (1 x 1 and 4 x 4 grids), two AOIs in different UTM zones, ML-boundary name scan (feature specs, columns, manifests, API schemas) and absence of torch/cv2/sklearn. Not met: anything requiring real data.

## Verification table (2026-11-14)
| Check | Result |
|---|---|
| Baseline before Phase 5 code | backend 493 passed / 4 skipped; `alembic check` clean; frontend tsc/lint clean, vitest 87 passed, build ok |
| Backend `pytest` after Phase 5 (throwaway DB `precursor_t_p5`, Earthdata unset) | **599 passed, 4 skipped** (106 new: terrain 15, tiling/texture/change/registry/schema 30, pipeline 14, dataset 41, API/CLI/boundary 6) |
| `alembic check` | no drift; no migration added (head 0005) |
| Frontend | tsc clean, vitest 87 passed (8 files), build passes; no frontend change |
| Docker image (rebuilt by the user) | scikit-image 0.26.0, scipy 1.18.1, pyarrow 26.0.1 import in the container (Python 3.12.16); registry loads; torch/cv2/sklearn absent; health ok; image 923 MB -> 1.46 GB |
| Live container run, **SYNTHETIC** temporary data (512 x 512, 30 m, EPSG:32650, 12 fabricated events; deleted afterwards, cleanup verified) | extract 12.2 s, peak child RSS ~270 MB, 17 DONE / 3 NOT_AVAILABLE; dataset 6.6 s: 10 of 12 events used (2 excluded with reasons), 20/20 background, 30 rows x 45 columns, leakage ok, dynamic columns all null; both API routes served the same content |
| Any real file or real catalog | **never performed** |

## Known limitations
See [PROJECT_STATUS](../project/PROJECT_STATUS.md) issues 35-40. Main points: untuned parameters and no real-data comparison; unverified `location_accuracy` vocabulary and buffer rule; dynamic features deferred; change features unavailable with the current stack; scale untested above 512 x 512 for dataset sampling; lineament density not tile-invariant; texture on a block grid and not sampled per point; image size +537 MB.

## Dependencies
Previous: Phases 3 and 4. Next: Phase 6 fills the reserved dynamic columns (lead-time anchors t-1/3/7/14/30 d) and decides the background reference date; Phase 7 validates a future model against `ModelInputSpec` through its model registry. Neither starts without the user's authorization.
