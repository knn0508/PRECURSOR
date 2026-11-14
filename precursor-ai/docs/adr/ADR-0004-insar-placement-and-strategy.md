# ADR-0004: InSAR code lives in the backend; delegate heavy SAR processing to external tools

- Status: ACCEPTED
- Date: 2026-11-14 (Phase 3)

## Context
The Phase 3 brief suggested `ai_engine/insar/`. The Docker backend image is built from `./backend` only, so `ai_engine/` code would not be deployable or importable by the API. Phase 2 already placed its real code in `backend/app/services/data_acquisition/` and left `ai_engine/data_acquisition` as a README. The environment has numpy, h5py, rasterio, pyproj, shapely but no scipy, SNAP, ISCE, MintPy, SNAPHU or GDAL CLI.

## Decision
1. Put Phase 3 in `backend/app/services/insar/` (adapters, inspection, scientific functions, outputs, run service). `ai_engine/insar/README.md` points there.
2. Product-aware adapters. GUNW (already unwrapped) is processed deterministically with numpy/h5py/rasterio. GSLC/GCOV are inspection only. Sentinel-1 SLC is inspection plus a gated external-tool interface.
3. Do not implement phase unwrapping or a TOPS processor. Use established tools (SNAP gpt, ISCE2/3, SNAPHU) when installed; until then runs end `BLOCKED_MISSING_INPUT`. MintPy is a time-series tool (Phase 6 scope), not an SLC processor.
4. Discover HDF5 datasets by name instead of hard-coding unverified paths.
5. Persist runs in two tables (`insar_processing_runs`, `deformation_products`); stage history and the quality report are JSONB because they are only read with the run. In-process single-worker executor (SAR jobs are memory heavy), consistent with [ADR-0003](ADR-0003-nasa-provider-abstraction.md).
6. Install `libexpat1` in the backend image (rasterio needs it).

## Alternatives considered
`ai_engine/insar` as a separate package (needs build-context and packaging changes; rejected for now). Writing our own unwrapper (rejected: unvalidated science). Four tables incl. stages and quality (rejected: extra joins, no extra queries). Installing SNAP/ISCE in the image (rejected: very heavy, untestable without real data).

## Consequences
Deployable now; real Sentinel-1 processing requires a future decision on which toolchain to install. Adapter field names may need fixing after the first real file. If `ai_engine` later becomes a package, scientific modules can move with import changes only.

## Related
[INSAR_METHODOLOGY](../scientific/INSAR_METHODOLOGY.md), [PHASE_03](../phases/PHASE_03.md)
