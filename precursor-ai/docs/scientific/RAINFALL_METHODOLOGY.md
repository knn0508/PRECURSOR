# Rainfall methodology (Phase 4, IMERG daily)

Status: implemented and tested on SYNTHETIC files only. `REAL_DATA_VALIDATION: NOT_PERFORMED`. No real IMERG file has been read.

## 1. Product facts: verified vs assumed

Official-documentation access in this session was limited (GES DISC pages render no content to the fetch tool; two
GPM PDFs were unreadable or 404). Only the items below were actually seen in official text.

| Fact | Status | Source |
|---|---|---|
| IMERG is offered at half-hourly, daily and monthly resolution | VERIFIED | https://gpm.nasa.gov/data/imerg |
| Final Run latency "about 3.5 months" (the same page also says "roughly 2.5 months" in another section) | VERIFIED, with the page itself inconsistent: this project uses the more conservative 3.5 months | https://gpm.nasa.gov/data/imerg |
| In V07 the variable is called `precipitation` (formerly `precipitationCal`); NASA recommends it for general use | VERIFIED (NASA IMERG V07 FAQ, via search excerpt) | https://gpm.nasa.gov/sites/default/files/2025-02/FAQ%20for%20IMERG%20V07%20Applications%20Users_202502.pdf |
| Half-hourly Final product has `Grid/probabilityLiquidPrecipitation` (percent) and `Grid/randomError` (mm/hr) | VERIFIED for HALF-HOURLY only (search excerpt) | https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGHH_07/summary |
| Phase 2 selects collection `GPM_3IMERGDF` (daily) via CMR | VERIFIED in repo code | backend/app/services/data_acquisition/providers/gpm.py |

ASSUMED, NOT VERIFIED (the reader discovers/checks these instead of trusting them):

- Daily file group/variable path (`/Grid/precipitation` assumed), dimension order (assumed `time, lon, lat`; the reader
  handles any order via dimension scales or unambiguous sizes and refuses square grids without scales).
- Daily units mm/day (the reader REQUIRES a units attribute that says mm/day; mm/hr and anything else are refused;
  a missing units attribute is accepted with a warning).
- Grid 3600 x 1800 at 0.1 degree, fill value (-9999.9 is only what the synthetic generator uses; the reader uses the
  file's `_FillValue`/`missing_value`), time coordinate and the daily-day convention (UTC day assumed).
- Daily variable set (whether `probabilityLiquidPrecipitation`/`randomError` exist in the daily file). These are not used.

## 2. AOI statistic

- Only the index window around the AOI bbox (plus one cell) is read.
- Cells whose CENTRE lies inside the AOI polygon (EPSG:4326) are averaged (valid cells only); min, max, cell count and
  valid-cell count are kept per day.
- AOI smaller than a cell: the single cell containing the AOI centroid is used, with an explicit warning that the value
  is a ~10 km cell value, not local rainfall.
- AOI outside the grid: `NotAvailable`. Partially overlapping AOIs use the cells that exist; coverage is reported.
- Aggregating or sub-selecting cells never increases the information resolution (~0.1 degree).

## 3. Missing-data policy

Missing is NaN/None, never zero. A calendar with every day from start to end is built; unobserved days stay missing.
No interpolation, gap filling or forecasting. Monthly sums exist only if every calendar day of that month (the full
month, including days outside the requested window) is observed; otherwise `observed_days/expected_days` is reported and
the sum is null. Rolling 3/7/30-day sums (configurable) require the entire trailing window to be observed. Files that
are corrupt, wrong-units or out of window are recorded per file and do not stop the run; status becomes
`PARTIALLY_PROCESSED`. Conflicting duplicate dates raise an error; identical duplicates are counted once with a warning.
A day whose AOI cells are all fill is treated as missing.

## 4. Rate vs accumulation

Daily-product values are treated as mm/day accumulations (SOURCE_OBSERVATION, per day). Monthly and rolling sums are mm
(DERIVED_MEASUREMENT). A rate in mm/hr is a different quantity: `rate_to_accumulation_mm(rate, step_hours)` multiplies by
the step length (half-hourly: x0.5 h). It is tested but NOT wired into the pipeline.

## 5. Latency and limitations

- Final Run latency is about 3.5 months: not real-time, not suited to monitoring current conditions.
- ~0.1 degree (~10 km) cells do not represent point or slope-scale rainfall.
- Satellite-based gauge-calibrated estimate, not gauge truth; uncertainty (`randomError`) is not propagated here.
- Daily totals follow the product's day definition (assumed UTC), not local time.
- Outputs are descriptive. No thresholds, risk language, scores or ML.

## 6. Half-hourly product (optional)

Status: **IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA** (synthetic fixtures only). Daily remains the default;
`process_rainfall_half_hourly` (`rainfall/half_hourly.py`) returns the same `RainfallResult`.

Verification of the official format (attempted 2026-11-14; the official PDFs/DMR were not machine-readable or the host
certificate had expired, so most items stay UNKNOWN and are NOT assumed by the code except where stated):

| Fact | Status | Source |
|---|---|---|
| Product GPM_3IMERGHH V07, half-hourly, 0.1 x 0.1 degree merged fields | VERIFIED | https://registry.opendata.aws/nasa-gpm3imerghh |
| `precipitation` is the data field of choice (calibrated) | VERIFIED | same page |
| File name pattern `3B-HHR.MS.MRG.3IMERG.YYYYMMDD-Shhmmss-Ehhmmss.MMMM.V07B.HDF5`; S/E = interval start/end, MMMM = minute of day of start (V07B Final example `20000601-S000000-E002959.0000`; NRT examples end `...-S233000-E235959.1410...`) | PARTLY VERIFIED (NRT names on the NASA page; Final name and S/E/minute reading from a search result, not a fetched page) | https://gpm.nasa.gov/data/news/latest-information-gpm-nrt-system-and-imerg-v07-updates ; https://eosdap.hdfgroup.org/opendap/data/hdf5/3B-HHR.MS.MRG.3IMERG.20000601-S000000-E002959.0000.V07B.h5.info (fetch failed: expired certificate) |
| 48 files per UTC day (30-min intervals S..E29:59) | INFERRED from the naming pattern, not read from a document | - |
| Time variable: seconds since 1980-01-06 00:00:00 UTC; grid 3600 lon x 1800 lat | SEARCH-SNIPPET ONLY, not verified | same .info page |
| Units of `precipitation` = mm/hr | UNKNOWN (not readable from official text here); the code REQUIRES an mm/hr units attribute, warns if it is absent and refuses mm/day | IMERG V07 Technical Documentation (PDF, unreadable by the fetcher): https://gpm.nasa.gov/sites/default/files/2023-07/IMERG_TechnicalDocumentation_final_230713.pdf |
| Fill value, dimension order, `probabilityLiquidPrecipitation`/`randomError` names | UNKNOWN (variables/axes are discovered by name; `_FillValue` read from the file; axes from dimension scales) | - |

Rules implemented:

- **Rate vs accumulation.** Values are mm/hr RATES. Each interval becomes an accumulation = rate x 0.5 h
  (`rate_to_accumulation_mm`). A rate file is refused by the daily reader and a daily file is refused by the rate reader.
- **48-interval completeness.** A UTC day is observed only if all 48 intervals are present and valid (an interval whose
  AOI cells are all fill counts as missing). Daily = sum of 48 accumulations. Partial days are `observed=false`, value
  null, with `intervals_observed`/`intervals_expected` on each daily record and `counts.partial_days`; zero-interval
  days are plain missing. Monthly/rolling sums reuse the unchanged complete-period rule.
- **Partial days are not scaled up.** Extrapolating 47/48 intervals (or any gap) would invent rainfall in the missing
  half-hour(s), which can be the heaviest ones; missing stays missing, never zero, never interpolated.
- Duplicate interval timestamps: identical values counted once with a warning, different values raise `EnvError`.
  Off-grid timestamps and files outside the window are ignored with a warning; corrupt files are recorded per file.
- Provenance: DERIVED_MEASUREMENT (accumulation derived from rate observations); `input_hash` includes
  `product='half_hourly'`.

Caveats: Final Run latency (~3.5 months) is unchanged, and half-hourly is not better in spatial resolution (~0.1
degree); sub-daily timing from a ~10 km satellite estimate is uncertain. Day boundaries are UTC.
