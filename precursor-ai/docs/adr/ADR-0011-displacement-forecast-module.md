# ADR-0011: Displacement-forecast module (second ML area), read-only serving

- Status: ACCEPTED
- Date: 2026-11-15 (user decision, in writing: "Add Farid's displacement-forecast models as a separate module (ai_engine/time_series ...) ... Label outputs research, inferred, not warning")
- Amends [ADR-0009](ADR-0009-ml-development-track.md) (ML only in `ml/`) and the `ai_engine/time_series/README.md` "must not hold a forecasting model" note. Does not change ADR-0002/0008.

## Context
The susceptibility track (`ml/`, M0-M9) stays as is and is still blocked only on the M5b label approval. A teammate repository (github.com/Farid145678/NASA_SPACE_APPS, commit 2a5f911) contains a separate, dynamic product: 12-day LOS displacement-increment forecasting from OPERA DISP-S1 time series with quantile outputs (MLP/GRU/LSTM, TCN, LSTM-TCN, onset head, Kalman baselines).

## Decision
1. **Code** lives in `ai_engine/time_series/displacement_forecast/` (ported, not rewritten; tests in `tests/`). It has its own environment (`ai_engine/time_series/requirements.txt`, CUDA torch 2.11.0+cu128) at `.venv-displacement/` (outside `ai_engine/`: the Phase 10 test forbids weight-like files there). It is not part of the backend image.
2. **Serving** is read-only: `backend/app/services/displacement_forecast/` + `GET /api/v1/displacement-forecast/*` read a precomputed result bundle in `data/displacement_forecast/` (copied unmodified from the source repo, see its `SOURCE.md`). The backend never runs the model. `PREDICTION_BACKEND` stays `none`; `/prediction/*` is untouched.
3. **Labelling:** every response and page says research / inferred / not a warning / not a landslide probability. NaN is "no reliable estimate", never zero.
4. **Not validated here:** numbers are the source author's; this project has not re-run training, downloaded OPERA/NISAR, or reproduced them. Source limitations (single site, repeated test inspection, masked landslide core, marginal gain over ridge) are shown in the UI.
5. **Data rule unchanged:** the ported OPERA/NISAR/IMERG fetchers (`opera.py`, `discovery.py`, `ancillary.py`, `remote.py`) are not run without the user approving specific files. NISAR is an observation layer only, never a model input.
6. The susceptibility track and this module are independent products (static map vs dynamic forecast); neither feeds the other.

## Consequences
- ADR-0009's "nothing wired into backend/frontend" applies to `ml/` only; this module is wired read-only by this decision.
- Port: v3 NISAR/geometry/state-space modules are ported too (58 tests). Scripts and notebooks are not. `backend` gained an OPERA DISP-S1 search provider (`ProviderName.OPERA`, `ENABLE_OPERA`, search needs no login; downloads follow the approval rule).
