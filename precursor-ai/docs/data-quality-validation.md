# Data quality and validation

`FileValidationService` (`validation_service.py`) runs structural checks on a downloaded file and returns a `ValidationReport`. It never raises on a bad file; failures become failed checks.

> **`VALIDATED` means the file passed integrity checks. It is NOT a scientific validation** of the data, of NISAR product quality, or of any displacement/landslide interpretation.

## Checks

All checks always run; the report is `ok` only if all pass. The report (with SHA-256, size and extracted fields) is stored in `data_acquisitions.validation_report`.

| Check | Passes when |
|---|---|
| `file_exists` | Path is a regular file. |
| `size_gt_zero` | Size > 0 bytes. |
| `checksum` | SHA-256 computed; and if a provider checksum is supplied (e.g. NISAR MD5), it matches. A checksum without an algorithm fails. |
| `format_opens` | The file opens with its format handler (below). |
| `product_type_matches` | The product type read from the file equals the granule's. Passes if the file has no such field. |
| `dates_valid` | Granule dates not before 1970, not in the future, start <= end; file-embedded start/end (if present) parse, are ordered, and the start is within 24 h of the catalog start. |
| `footprint_valid` | Granule footprint is valid, non-empty and within lon/lat bounds. Passes if there is no footprint. |
| `version_and_maturity_recorded` | Granule version non-empty; NISAR granules also need a maturity. |

## Per-format handling

| Extension | Handler |
|---|---|
| `.h5 .hdf5 .nc .nc4` | `h5py` open. If `/science/LSAR/identification` exists, reads `productType`, `granuleId`, `boundingPolygon`, `zeroDopplerStartTime`, `zeroDopplerEndTime` when present. A NISAR-style `.h5` (has `science` group) without that group fails. Other HDF5/NetCDF files pass if they open (IMERG `.nc4` falls here). |
| `.tif .tiff` | `rasterio` open; needs positive dimensions and a CRS. |
| `.hgt` | Size must be 3601x3601x2 (1 arc-second) or 1201x1201x2 (3 arc-second) bytes. |
| `.zip` | Zip integrity (`testzip`), non-empty; any `.hgt` inside must have a valid size (NASADEM tiles). |
| `.csv` | Header row non-empty. |
| other | Fails: unsupported extension. |

## What is and is not confirmed

- The NISAR HDF5 layout (`/science/LSAR/identification`: `productType`, `granuleId`, `boundingPolygon`) was **only partly confirmed from a documentation search, not from a real file**. The start/end time keys (`zeroDopplerStartTime`/`zeroDopplerEndTime`) are **unconfirmed**; missing keys are tolerated, so the date cross-check may silently not run on real files.
- No real NISAR, NASADEM or IMERG file has been validated. Tests use synthetic files.
- The `.hgt` check applies to a bare `.hgt`; the NASADEM zip check inspects entries inside the zip. Real NASADEM zip contents were not inspected.

## Re-running

`revalidate` (CLI) / orchestrator `revalidate(acquisition_id)` re-runs the checks on the stored local file and rewrites the report and manifest. On failure the acquisition becomes `FAILED` with the failed checks in `error_message`.

## Environment pitfall: PROJ_LIB

A machine-level PostgreSQL/PostGIS install can set `PROJ_LIB` to an older `proj.db` that shadows pyproj/rasterio's bundled data, causing CRS errors. The test suite works around it with `monkeypatch.setenv("PROJ_LIB", pyproj.datadir.get_data_dir())`. A shared fix module `app/core/geo_env.py` does **not** exist in the repo at the time of writing; if you hit this outside tests, set it yourself:

```bash
export PROJ_LIB="$(python -c 'import pyproj; print(pyproj.datadir.get_data_dir())')"
```
