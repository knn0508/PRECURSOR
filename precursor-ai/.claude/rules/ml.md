---
paths:
  - "ml/**"
  - "data/ml/**"
  - "docs/ml/**"
---

# ML track rules (ADR-0009; source: Prompts.md "Track rules")

- **Location:** all ML code, notebooks, configs, reports and experiment outputs live under `ml/` (data under `data/ml/`). Existing backend code (Phases 2-5, incl. `features_cv`) may be imported and reused **read-only**; never modify it. A bug found there is reported; fixed only with the user's approval and a regression test.
- **Real data only for performance claims.** Synthetic data only for pipeline smoke tests, always labelled; a model trained or scored on synthetic data is never reported as a result.
- **No downloads or Earthdata login** without the user's approval of specific files (name, source, size, AOI, total GB, disk/time). Never print credentials. Large-data steps stop and ask.
- **Scientific integrity:** every metric on held-out data (spatial-block CV, plus temporal hold-out where dates exist); never report training or tuned-fold scores as performance; report negative and weak results honestly; state the inventory-bias caveat (catalogs are incomplete and biased to reported, accessible places); absence of a record is not proof of stability: say "background", never "negative". Labels must be temporally compatible with the satellite data used.
- **No leakage:** spatial buffers, temporal cut-offs, no future information in features, no random pixel splits.
- **Reproducibility:** fixed seeds, pinned versions, dataset hashes, code version and config logged per run; one command re-runs each stage. Convention: [EXPERIMENT_LOG](../../docs/ml/EXPERIMENT_LOG.md).
- **Dependencies:** list and justify every new package before installing; ML environment stays separate from the backend image (`ml/requirements.txt`).
- **Docs:** each stage ends with `ml/reports/M<n>_*.md` and updates `docs/ml/ML_STATUS.md`, TASK_LOG and CHANGELOG; PROJECT_STATUS gets one "ML track" line and no roadmap status changes. Unverified = `NOT_VERIFIED`.
- **Stop points:** M1, M5, M7, M9 wait for the user's explicit answer. Never start the next M-stage on your own.
- Each stage report ends with: what was done, real results, what was not verified, risks, decision needed.
- Nothing from the track is wired into backend, frontend, API or DB; `PREDICTION_BACKEND` stays `none`. Run `python ml/scripts/check_scope.py check` before finishing a stage.
