# models/ : reserved ML slot (no weights, no model)

Layout read by `backend/app/services/prediction/registry.py`: `models/<model_id>/<version>/metadata.json` plus the model card it names.
Folders starting with `_` (the template) and `checkpoints/`, `evaluation/` are not models and are ignored.

**This folder holds no trained model.** Nothing here may be a rule-based scorer. A model is added only in a separately authorized stage
(gate: real dated inventory, real Phase 4-6 features, approved validation protocol, approved model family and compute budget).
How to add one: [docs/architecture/ML_INTEGRATION.md](../docs/architecture/ML_INTEGRATION.md). Start from `_template/0.0.0/`
(`metadata.template.json`, `MODEL_CARD.template.md`); rename the metadata file to `metadata.json` only for a real model.
