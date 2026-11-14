# ai_engine

Scientific processing code for PRECURSOR AI. **Phase 1 contains no implementations**: every subdirectory has a README stating its future responsibility and scientific constraints.

Planned data flow (each stage reads/writes files under `data/` and metadata in PostgreSQL):

```
data_acquisition -> preprocessing -> insar -> time_series -> risk_assessment
                                      \-> computer_vision ->/        |
                                                      uncertainty + explainability
```

Note: Phase 4-5 deterministic code lives in `backend/app/services/` (environmental, features_cv); the ML slot (Phase 7) is `backend/app/services/prediction/`. `ai_engine/` stays README-only until a real model is separately authorized.

Rules for all modules:

- Label every output as `measured` (derived from real satellite data), `synthetic` (demo/test), or `predicted` (model output).
- Never present an uncalibrated risk score as a probability.
- Keep time-series splits chronological. No random shuffling across time.
- Modules are pure Python packages with no FastAPI imports. The backend calls them through `backend/app/services`.
