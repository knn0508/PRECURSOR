# SMAP soil moisture: methodology

Status: **IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA**. Tested only with labelled synthetic fixtures (`app/services/environmental/smap/synthetic.py`). `REAL_DATA_VALIDATION: NOT_PERFORMED`.

Code: `smap/reader.py` (one file -> AOI statistic per overpass), `smap/smap_processor.py` (files -> daily calendar), `features/smap_features.py` (descriptive features).

## 1. Product facts (VERIFIED vs UNKNOWN)

Sources read: NSIDC SPL3SMP_E V006 user guide (https://nsidc.org/sites/default/files/documents/user-guide/spl3smp_e-v006-userguide.pdf), V001 user guide (https://nsidc.org/sites/default/files/documents/user-guide/spl3smp_e-v001-userguide.pdf), product page (https://nsidc.org/data/spl3smp_e/versions/6). The V006 guide's text was extracted locally; section/table numbers below refer to it.

| Fact | Status | Source |
|---|---|---|
| Phase 2 default collection SPL3SMP_E (enhanced 9 km radiometer daily) | VERIFIED (repo, `settings.smap_collection`) | Phase 2 provider |
| HDF5 groups `Soil_Moisture_Retrieval_Data_AM`, `_PM` (and `_Polar_AM/_PM`, `Metadata`) | VERIFIED | V006 guide 1.1, 1.2.2, Appendix |
| PM variable names carry the suffix `_pm` | VERIFIED | V006 guide 1.1 note |
| Variables `soil_moisture`, `retrieval_qual_flag`, `surface_flag`, `latitude`, `longitude`, `tb_time_utc`, `EASE_row_index`, `EASE_column_index` | VERIFIED (names, types, units, fill) | V006 Table A-1 |
| Fill/gap value -9999.0 for soil_moisture, latitude, longitude; 65534 for retrieval_qual_flag | VERIFIED | V006 Table A-1 |
| Units of soil_moisture: m3/m3 (volumetric fraction). Valid range 0.02 to soil porosity | VERIFIED. The guide says **m3/m3**, not cm3/cm3. The two are numerically identical; the code accepts both spellings (`cm3/cm3`, `cm**3/cm**3`, `m3/m3`, `m**3/m**3`), refuses anything else, never converts. Provenance reports `cm3/cm3` plus a note | V006 1.1, Table A-1 |
| `retrieval_qual_flag` is a 16-bit flag: bit 0 = 0 recommended quality; bit 1 retrieval skipped; bit 2 retrieval unsuccessful; bit 3 freeze/thaw retrieval unsuccessful; bits 4-15 unused. "A value of either 0 or 8 indicates high-quality retrievals" | VERIFIED | V006 Table 6 / A-2, 2.5.3 |
| Grid: global cylindrical EASE-Grid 2.0, 9 km posting (9,024.31 m), 1624 rows x 3856 columns; EPSG:6933 (global) | VERIFIED | V006 Table 5; product page |
| Native radiometer footprint ~36 km; 9 km values are Backus-Gilbert interpolated | VERIFIED (V001 guide 1.9.1) | V001 guide |
| Daily composite of half-orbit swaths; descending (AM, ~6:00 LST at the equator) and ascending (PM, ~18:00) stored separately in the same file | VERIFIED | V006 1.2.3, 1.4.4 |
| Surface soil moisture represents about the top 5 cm of soil on average | VERIFIED | V006 1.1 |
| Swath ~1000 km, nearly global coverage every three days (so many cells have no observation on a given day) | VERIFIED (V001 guide, Spatial Coverage) | V001 guide |
| Coverage from 31 March 2015; gaps 19 Jun-23 Jul 2019 and 6 Aug-20 Sep 2022 (safe mode); other small gaps listed by the SMAP On-Orbit Events and Bad/Missing Data lists | VERIFIED | V006 1.4 |
| The SMAP radar failed on 5 July 2015 (the enhanced radiometer product does not depend on it) | VERIFIED (mentioned in the surface_flag description) | V006 2.5.3 |
| File name pattern `SMAP_L3_SM_P_E_yyyymmdd_RLVvvv_NNN.h5` | VERIFIED | V006 Table 3 |
| HDF5 attribute names for units / `_FillValue` in real files; dimensionality of real `latitude`/`longitude` (2-D vs 1-D); root attributes carrying short name / version | UNKNOWN (no real file opened) | handled by name discovery and warnings |
| Whether the real file stores a per-cell "no observation today" as -9999.0 in soil_moisture | UNKNOWN (fill value is documented, the coverage semantics per cell are not read from a file) | |
| SPL3SMP (36 km) layout and grid shape (inferred 406 x 964 from EASE-Grid 2.0 nesting; the V006 table lists EASE index maxima 963/405) | UNKNOWN / not verified; reader reports `native_resolution_km=None` for any grid other than 1624 x 3856 | |
| Revisit time as a single number | UNKNOWN beyond the ~3-day near-global statement above | |

## 2. AOI statistic

Per overpass (AM and PM separately), read only an index window around the AOI (not the global grid). Latitude/longitude are discovered by name; both 2-D arrays and 1-D axis vectors are supported. Cells whose **centre** lies inside the AOI polygon (EPSG:4326, shapely) are used. If none, the single cell containing the AOI centroid is used with an explicit warning: the value is a ~9 km cell value derived from a ~36 km footprint, not local soil moisture. A centroid farther than half a cell from any centre, or an AOI outside the grid, raises `NotAvailable`. Reported: `n_cells`, `n_valid`, min, max, mean (mean of valid cells; no area weighting).

Refusals (`EnvError`): units not a volumetric fraction; ambiguous or inconsistent axis order (lat varying along columns, equal-length axis vectors, shape mismatch); longitude in 0-360; missing `soil_moisture`. Missing units attribute: warning, volumetric fraction assumed. Fill: the declared `_FillValue`/`missing_value`, else the documented -9999.0 with a warning. Values outside 0..1 produce a warning only.

## 3. Missing-data policy

Complete calendar `start..end`. A day is **observed** when AM or PM has at least one valid AOI cell. Missing days, and overpasses with no valid cell, are `null`, never zero. No interpolation, gap filling, smoothing, forecast, anomaly or percentile scoring. Files outside the window are ignored with a warning; corrupt/unusable files are recorded in `file_errors` and processing continues (status `PARTIALLY_PROCESSED`); no usable file raises `NotAvailable`. Duplicate dates: identical values are collapsed with a warning; different values raise `EnvError` (no silent choice). `valid_percent` = observed days / expected days.

## 4. AM/PM rule

AM and PM are kept as separate series. The combined `soil_moisture` of a day is the mean of the AM and PM AOI values **only when both are observed**; otherwise it is `null` (a missing overpass is never averaged as zero and the other overpass is not promoted to the daily value).

## 5. Quality filter

`quality_filter=False` (default) keeps every non-fill cell. `True` keeps only cells whose `retrieval_qual_flag` has bits 0, 1 and 2 clear (equivalently 0 or 8 among the defined bits; the 65534 fill is never kept). If a file has no usable flag the filter is refused for that file (`EnvError`, recorded as a file error). The number of valid cells dropped is reported per overpass-day (`aoi_stats[].n_dropped_quality`) and in total (`quality_dropped_cells`). The filter uses the verified bit rule; it does not use `surface_flag`.

## 6. Limitations

- **Depth:** L-band emission reflects roughly the top 5 cm of soil. It is not root-zone, slope-scale, or sub-surface soil moisture, and it says nothing about moisture at a potential failure depth.
- **Resolution:** 9 km posting from a ~36 km footprint; an AOI of a few km is a single coarse-cell value.
- **Coverage:** near-global coverage only every ~3 days; masked surfaces (open water, urban, dense vegetation, frozen ground, steep topography, precipitation, snow) produce no or lower-quality retrievals per the flags.
- Descriptive only: no wetness classes, saturation statements, thresholds or risk wording. Data origin is `SYNTHETIC_FIXTURE` for fixtures, `REAL_SATELLITE` only when every file carries a Phase 2 acquisition id, else `LOCAL_UNVERIFIED`. Dataset version is reported only if the file states it, otherwise UNKNOWN.
