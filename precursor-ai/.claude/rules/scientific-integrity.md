# Scientific integrity rules

## Never
- Fabricate measurements, satellite acquisitions, dataset availability for an AOI, test results, uncertainty intervals or risk scores.
- Present synthetic/demo data as real satellite observations.
- Present deformation as proof of an imminent landslide.
- Present unvalidated risk scores as calibrated probabilities.
- Say a product exists for an AOI until the catalog confirms it. A metadata hit is not a downloaded file; a downloaded file is not scientifically validated.
- Silently mix product maturities (VALIDATED / PROVISIONAL / BETA). Store and show maturity with every granule.

## Always
- Distinguish observed measurements from derived metrics, and both from model output.
- Record provenance (source, collection, version, maturity, retrieval date, checksum) and data limitations.
- State dataset limits: Global Landslide Catalog is a one-time export whose last event is dated 2017-09-28 (corrected 2026-11-15, [M1 census](../../ml/reports/M1_census_and_download_list.md)), not complete or current; absence of an event proves nothing. IMERG is not real-time.
- Mark unverified claims `UNKNOWN` or `NOT_VERIFIED`.

## ML development policy (applies to every phase prompt)
All ML and DL models are placeholders in the current roadmap. Do not train, fine-tune, run real inference, emit fabricated scores/predictions, or replace a future model with hardcoded or rule-based predictions. Allowed: deterministic scientific processing (preprocessing, InSAR, DEM slope/aspect, displacement/velocity, statistics, feature extraction, quality assessment) and ML interfaces, schemas and service contracts. Real ML arrives only in a separately authorized phase after the roadmap is completed and reviewed. Also allowed ([ADR-0008](../../docs/adr/ADR-0008-ml-slot-and-labelled-mock-frontend.md)): the reserved ML slot (`services/prediction/`, default `PREDICTION_BACKEND=none`, returns `MODEL_NOT_TRAINED`, test-only `TEST_DOUBLE` in `tests/`) and clearly labelled MOCK prediction views in the frontend only (`MOCK DATA: NOT A PREDICTION`, flag default off, seeded, neutral palette, no export, never in backend/DB/API, never derived from real inputs). `ModelInputSpec` is the single model-input contract.

**ML track exception ([ADR-0009](../../docs/adr/ADR-0009-ml-development-track.md)):** ML development is permitted ONLY inside the ML track (`ml/`, `data/ml/`; rules in [ml.md](ml.md)); every other directory and every roadmap phase remains ML-free. All other rules in this file still apply inside the track (no synthetic results, no fabricated scores, real-data-only performance claims).
