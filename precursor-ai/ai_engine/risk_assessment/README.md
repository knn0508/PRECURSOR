# risk_assessment

**Status: placeholder, no code.** The reserved ML slot lives in `backend/app/services/prediction/` (Phase 7, [ADR-0008](../../docs/adr/ADR-0008-ml-slot-and-labelled-mock-frontend.md)); this directory must not hold a model, a rule-based scorer or fabricated outputs. "Risk score" below is the future model's output; there is none today.

**Future responsibility:** combine deformation features with terrain/environmental factors (slope, rainfall, lithology, land cover) into a landslide **risk score** per area/zone.

Scientific constraints:

- A score is not a probability unless calibrated against an independent landslide inventory. Until then, call it a "relative risk score".
- Evaluate with appropriate metrics (precision/recall, PR-AUC, ROC-AUC, Brier score/calibration for probabilities) on spatially and temporally held-out data.
- Persisted predictions (future tables) must store model version, input data version and uncertainty.
