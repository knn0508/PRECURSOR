# Deformation metrics

Implemented in Phase 3 (`backend/app/services/insar/`). Verified only with synthetic arrays and a hand-computed oracle. Never validated on real satellite data. Equations and conventions: [INSAR_METHODOLOGY](INSAR_METHODOLOGY.md).

| Metric | Unit | Kind | Definition |
|---|---|---|---|
| Unwrapped phase | rad | **existing product measurement** (input) | Read from the GUNW as delivered; never modified |
| Coherence magnitude | dimensionless 0-1 | **existing product measurement** (input) | Preserved as delivered; invalid values -> no-data |
| LOS displacement | mm | **newly derived** | `-(lambda/4*pi) * phase * 1000`; relative to an unspecified reference; positive = toward satellite (assumed, unverified) |
| LOS velocity | mm/year | **newly derived** | displacement / (temporal baseline / 365.25 d); mean over one interferogram |
| Per-raster statistics | same as raster | derived summary | valid and no-data pixel counts, no-data %, mean, std, min, max (online, block-wise) |
| Coherence statistics | - | derived summary | valid/invalid counts, mean, min, max, optional fraction below the user threshold |

Rules:
- Observed (input) and derived values are labelled separately in every quality report (`measurement_kinds`).
- No uncertainty is reported: none is computed, and none is invented.
- A deformation raster measures motion along the radar line of sight. It is not 3D displacement, not proof of a landslide, and not a risk score or probability.
- Synthetic outputs carry `DATA_ORIGIN=SYNTHETIC_FIXTURE` and the API/UI label them "SYNTHETIC TEST DATA".

Not implemented (later phases): time-series velocity, forecasting (Phase 6), reference-point selection, atmospheric correction, uncertainty (Phase 8).
