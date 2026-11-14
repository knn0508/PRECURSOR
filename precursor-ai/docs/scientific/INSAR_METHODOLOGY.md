# InSAR methodology (Phase 3)

Status: **implemented and tested on SYNTHETIC fixtures only. `REAL_DATA_VALIDATION: NOT_PERFORMED`.** No real NISAR or Sentinel-1 file has been processed (none has been downloaded). Code: `backend/app/services/insar/` (not `ai_engine/insar/`: the Docker backend image contains only `backend/`, and Phase 2 also keeps its real code under `backend/app/services/`; see [ADR-0004](../adr/ADR-0004-insar-placement-and-strategy.md)).

All processing is deterministic. No ML.

## Product-aware processing paths

| Input | What the system does | What it will not do |
|---|---|---|
| **NISAR GUNW** (geocoded, unwrapped) | Inspect HDF5 -> discover datasets by name -> validate -> LOS displacement (mm), coherence raster, mean velocity (mm/yr) | Re-run SLC interferometry; assume a layout without checking; apply any atmospheric correction |
| **NISAR GSLC** (geocoded complex, one date) | Inspect; list complex layers; preserve phase in the file; quality/inspection report | Derive displacement from one date. A pair needs an interferogram plus unwrapping by an external tool |
| **NISAR GCOV** (covariance/backscatter) | Inspect; list covariance terms and polarizations | Treat as interferometric. There is no phase, so no displacement |
| **Sentinel-1 SLC** | Recognise the SAFE/zip name, read archive listing, report which external tools exist | Process. `BLOCKED_MISSING_INPUT` until SNAP or ISCE (plus SNAPHU) is installed and workflow templates are written |

Stage selection per product (the run records every stage as DONE / SKIPPED / ABORTED):
GUNW `INSPECTING -> PREPROCESSING (skipped: already geocoded/unwrapped; checks only) -> DISPLACEMENT_CALCULATION -> QUALITY_CHECK`. GSLC/GCOV `INSPECTING -> (skipped) -> QUALITY_CHECK`, ending COMPLETED with no raster ("inspection-only"). Sentinel-1 ends `BLOCKED_MISSING_INPUT`. Unsupported GUNW metadata ends `FAILED`: a required scientific check failed, so processing stops.

## HDF5 layout: what is and is not known

The exact NISAR HDF5 dataset paths have **not** been confirmed against a real granule here (see [GUNW overview](https://nisar-docs.asf.alaska.edu/gunw/) and spec JPL D-102272, whose current revision must be checked). The inspector therefore **discovers datasets by name** (`unwrappedPhase`, `coherenceMagnitude`, `connectedComponents`, `xCoordinates`, `yCoordinates`, `projection`, `centerFrequency`, identification fields) and reports what it found and what is missing. Synthetic fixtures mimic the believed layout and say so. If a real file differs, expect adapter fixes: that is the first thing the manual real-data test (below) checks.

## Equations and conventions

- Wavelength: `lambda = c / f` from the file's centre frequency (c = 299 792 458 m/s). Rejected outside 5 mm to 1 m (unit error guard).
- LOS displacement: `d_LOS = -(lambda / 4*pi) * delta_phi`, `delta_phi` = unwrapped differential phase in radians; result in metres, stored in **mm**. One fringe (2*pi) equals `lambda/2` of LOS motion.
- **Sign:** under this convention positive displacement is *toward the satellite*. The phase sign convention of the NISAR product has **not** been verified, so every output carries `SIGN_CONVENTION_VERIFIED=false`. The sign is only as correct as that assumption.
- Phase must be unwrapped and differential (topography/orbit removed by the producer). This is **not verified** from the file; it is a stated assumption in every report.
- The result is relative: no reference point is applied. Values are meaningful as differences only.
- Velocity: `v = d / (dt_days / 365.25)` in mm/year, with `dt = secondary - reference`. It is the **mean over one interferogram's baseline**, assuming steady motion. It is not a time series and not a forecast (Phase 6). `dt <= 0` or missing dates -> velocity skipped with a warning. A two-product velocity function exists and refuses incompatible inputs (units, grid, CRS, orbit direction, relative orbit, shared reference date, date order).
- Coherence: delivered values are preserved. Valid range [0, 1] (with float slack); out-of-range, fill and NaN are no-data. Statistics only. The optional threshold is user-supplied, recorded in the run and **off by default**. It masks displacement pixels to no-data (not zero). No universal threshold exists.
- Optional connected-components mask (off by default). The meaning of component 0 is an assumption from product conventions, not verified.

## No-data policy

Missing, fill, NaN/inf and masked pixels are written as NaN with `nodata=NaN`, counted in statistics, and shown transparent in previews. Missing data is never converted to zero or filled with invented values.

## Implemented but not wired into runs

`interferogram.py` (wrapped interferogram from two co-registered complex SLCs, phase wrapping) and `coherence.estimate_coherence` (boxcar sample coherence) are unit-tested numpy functions. Phase unwrapping is **not** implemented: no unvalidated algorithm was written to force an output. An external-tool gate (`external.py`: availability, version, timeout, error and output checks, no shell) exists for SNAP/ISCE/SNAPHU. Its use is tested with a stand-in executable only.

## Outputs

`data/processed/insar/{displacement,coherence,velocity}/<run_id>/*.tif` (Cloud Optimized GeoTIFF via GDAL's COG driver, float32, nodata NaN, tags for units, dates, origin, sign convention, `SCIENTIFICALLY_VALIDATED=false`), plus `quality_reports/`, `inspections/`, `metadata/` JSON per run. A deformation raster is a measurement product, **not** a risk map (risk is Phase 7).

## External software

Used: numpy, h5py, rasterio (GDAL 3.12 bundled), pyproj, shapely. In the Docker image `libexpat1` is installed because rasterio needs it. **Not installed**: GDAL CLI, SNAP, ISCE, MintPy, SNAPHU, scipy. Tool choice for Sentinel-1 is in the adapter docstring and the ADR.

## Real-data validation: manual steps (not yet done)

1. User approves and downloads one real GUNW (Phase 2 workflow), or places a local file.
2. `REAL_INSAR_FILE=<path> pytest backend/tests/manual/test_real_insar.py -s`.
3. Check the printed inspection: found datasets, missing metadata, units, wavelength, dates.
4. Fix adapter name/layout mismatches; add a regression test from the corrected finding.
5. Verify sign convention and reference on a site of known motion (or against a published product) before claiming correctness.
6. Only then update status; until then every document says NOT_PERFORMED.
