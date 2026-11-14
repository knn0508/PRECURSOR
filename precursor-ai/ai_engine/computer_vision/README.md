# computer_vision

**Responsibility:** descriptive feature extraction from rasters (terrain relief, roughness, curvature, edge/lineament density, texture, change features). It extracts numbers; it does not classify, score or flag anything.

The implementation lives in `backend/app/services/features_cv/` (Phase 5, [ADR-0007](../../docs/adr/ADR-0007-feature-extraction-and-labelled-dataset.md)), not here; `ai_engine/*` must never import FastAPI and would duplicate the Phase 4 raster layer. This folder stays a pointer, like `ai_engine/insar`.

Scientific constraints: image *analysis* on top of InSAR and environmental products; it does not replace InSAR deformation measurement. No trained or pretrained model is run (ML policy, [ADR-0002](../../docs/adr/ADR-0002-ml-deferral.md)). Any future model must be trained and evaluated only on labelled, spatially-held-out data (see `docs/scientific/LABELLED_DATASET.md`).
