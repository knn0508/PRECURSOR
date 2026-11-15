# M2 acquisition report

Date: 2026-11-15. Approved list: user message of 2026-11-15 (B1 regions). Code: [m2_acquire.py](../scripts/m2_acquire.py) (reuses Phase 2 `cmr`, `AOI`, `tiles_for_aoi`, `EarthdataAuthenticationService`, `DownloadManager`, `hash_file` read-only; no database), [m2_verify.py](../scripts/m2_verify.py), tests [test_m2_acquisition.py](../tests/test_m2_acquisition.py). Plan: `ml/reports/m2_probe/m2_plan.json`; run log: `ml/reports/m2_probe/download_run1.log`. Per-file URL, licence, retrieval time, size and SHA-256: `data/ml/raw/manifest.json` and [DATASET_LOG](../../docs/ml/DATASET_LOG.md). Credentials were read by Phase 2 Settings from `.env`, never printed; a check of the log, manifest and plan found neither the user name nor the password.

## Status against the approved list (FINAL, 2026-11-15)
| Item | Approved | Arrived | Status |
|---|---|---|---|
| NASADEM_HGT 001 tiles | 27 tiles, 276.9 MB | 27 files, 290,365,900 B (= 276.9 MiB) | **COMPLETE**; zip test OK |
| ESA WorldCover 2021 v200 | 8 tiles, 497.2 MB | 8 files, 497,113,735 B | **COMPLETE**; all open in rasterio (EPSG:4326, 36000x36000 uint8) |
| IMERG monthly Final V07 | 199 files, 2001-06..2017-12, <= 5 GB | **199 files, 3,746,557,503 B (3.75 GB)**, largest 19.6 MB, months 2001-06 .. 2017-12 | **COMPLETE**. One test request first returned HTTP 200 (after the user approved the GES DISC app); 0 failures. All 199 have the HDF5 signature and open in h5py with `Grid/precipitation` (shape 1 x 3600 x 1800, float32). The catalog publishes no checksum |
| Lithology (user-approved substitute for SGMC) | CA, OR, WA state maps, <= 500 MB | 3 files, 45,561,757 B from `mrdata.usgs.gov/geology/state/shp/{CA,OR,WA}.zip` | **COMPLETE**; zips test OK; polygons CA 10,465, OR 12,349, WA 4,945 (EPSG:4326, 8 fields). Relation to SGMC v1.1: NOT_VERIFIED. The US-wide SGMC file was never fetched (ScienceBase Cloudflare challenge, not circumvented); no MISSING_FACTOR needed |

## Real totals
**237 files, 4,579,598,920 B (4.58 GB)** (NASADEM 27 + WorldCover 8 + geology 3 + IMERG 199); the 2 label files (10.1 MB) from the census are additional and are listed separately in DATASET_LOG. Limits: 30 GB total (ok), 2 GB per file (largest file 101.2 MB), free disk after downloads **46 GB** (>= 15 GB required). No unexpected size growth.

## Failures
None remain. History: IMERG returned HTTP 403 "EULA Acceptance Failure" twice before the user's authorisation (`download_run1.log`, `download_run2.log`); after authorisation the plan was re-run, a single test request returned 200, and `download_run4_imerg.log` shows 199 ok and 0 FAILED.

## Code-text correction (separate small change, user-approved)
GLC end-date strings 2016-03-07 -> 2017-09-28 in code and tests (text only; `EXPORT_DATE` is now "2017-09-28"; `DEFAULT_VERSION` stays the literal "export-2016-03-07"; regression test `backend/tests/test_glc_end_date.py`). Full backend suite (Earthdata credentials unset, throwaway DB `precursor_t_glcfix`, dropped afterwards): **601 passed, 4 skipped** (manual live tests), 137 s. Remaining docs now also say 2017-09-28 (3 scientific docs, PHASE_07, PROJECT_MEMORY); `docs/data-storage.md` is intentionally unchanged.

## Tests (real output)
`pytest ml/tests -q -c ml/pytest.ini` (re-run after the final download, see ML_STATUS for the count). `m2_verify.py`: 237 files, 0 failing integrity.

## What was not verified
Integrity only: nothing was read scientifically (no tile content, no CRS/vertical-datum check of NASADEM, no WorldCover class check). `VALIDATED` here means checksum/open-ability, not scientific validation. NASADEM/IMERG licence text is not verified. NASADEM has no published checksum in the catalog (`published_checksum` empty), so the SHA-256 is our own record, not an upstream comparison. The Phase 2 `FileValidationService` was not used (it needs database granule records); integrity was checked by `m2_verify.py` instead.

## Risks
Rainfall record may be limited to the 33 approved months; lithology source unresolved; GLC location accuracy ~5 km vs 30 m source rasters (M3 grid decision, see ML_STATUS conditions).

## Decision needed from you
None blocking. M2 is complete; M3 (preprocessing) starts only on your instruction. Conditions already recorded for M3 in ML_STATUS: analysis-grid cell size consistent with the ~5 km GLC accuracy; one documented lithology class system across the three state legends (record the mapping and every unmapped class).
