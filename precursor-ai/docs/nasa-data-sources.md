# NASA data sources

Catalog facts below were checked with anonymous CMR queries on **2026-11-14**. Catalogs change; the code re-verifies existence at runtime and never assumes a collection exists. Nothing here was verified by downloading a file.

| Provider | Collection (short name, version) | DAAC | Config |
|---|---|---|---|
| NISAR | `NISAR_L2_{GUNW,GCOV,GSLC,GOFF}_V1` (+ `_PROVISIONAL_V1`, `_BETA_V1`), `NISAR_L3_SME2_{PROVISIONAL,BETA}_V1` | ASF | `ENABLE_NISAR`, `NISAR_PRODUCTS`, `ALLOWED_MATURITIES` |
| NASADEM | `NASADEM_HGT` 001 | LPCLOUD | `ENABLE_NASADEM` |
| GPM IMERG | `GPM_3IMERGDF` 07 (default), `GPM_3IMERGHH` 07, `GPM_3IMERGM` 07 | GES_DISC | `ENABLE_GPM`, `GPM_RESOLUTION` |
| SMAP | `SPL3SMP_E` 006 (default) | NSIDC | `ENABLE_SMAP=false`, `SMAP_COLLECTION` |
| Landslide catalog | NASA Open Data Portal CSV export | none | `ENABLE_LANDSLIDE_CATALOG` |

## NISAR

All NISAR collections are provider ASF, version `"1"`. Example concept id: `C3622247503-ASF` (`NISAR_L2_GUNW_V1`). The collection name is built as `NISAR_{L2|L3}_{PRODUCT}[_PROVISIONAL|_BETA]_V1`; the unsuffixed name is the validated one.

Verified present: `NISAR_L2_{GUNW,GCOV,GSLC,GOFF}_V1` (validated), and the same four with `_PROVISIONAL_V1` and `_BETA_V1`.

**Soil moisture exists only as `NISAR_L3_SME2_PROVISIONAL_V1` and `NISAR_L3_SME2_BETA_V1`. There is no validated `NISAR_L3_SME2_V1`** (an example id in the original spec does not exist in the catalog). Searching `SME2` with default settings therefore returns nothing and a warning "no VALIDATED collection exists for SME2".

### Product types

| Product | What it is | Use / caution |
|---|---|---|
| GUNW | Geocoded unwrapped interferogram | Basis for phase-derived line-of-sight (LOS) displacement. It is **not** a landslide detection. |
| GCOV | Geocoded polarimetric covariance | Backscatter. |
| GSLC | Geocoded single-look complex | Complex SAR data for custom interferometry. |
| GOFF | Geocoded pixel offsets | For larger displacements than phase can track. |
| SME2 | Soil moisture | Only PROVISIONAL/BETA exist (see above). |

### Maturity

| Level | Meaning in this project |
|---|---|
| `VALIDATED` | Collection without a suffix. **Default**: `ALLOWED_MATURITIES=VALIDATED`. |
| `PROVISIONAL` | Lower maturity; explicit opt-in; always labelled on results, rows and manifests. |
| `BETA` | Lowest maturity; explicit opt-in; always labelled. |

Granules of different maturities are never merged: each record carries its maturity and collection short name. Results sort VALIDATED first. A search requesting a maturity not in `ALLOWED_MATURITIES` is rejected.

### Granule facts

- A real GUNW granule is about 1.4-2.0 GB (HDF5). MD5 is published in the catalog metadata and kept in `metadata_json['published_checksum']`. The sample seen had a 12-day temporal baseline (`temporal_baseline_days` is computed from reference/secondary start times).
- A granule also carries PNG browse files; the pipeline ignores them and downloads only the `.h5` file.
- Relative orbit comes from the `TRACK_NUMBER` attribute, not from the first number in the granule id.
- Search uses `cmr.py` (earthaccess). `ASFSearchProvider` (asf_search library) is search-only and acts as a fallback when every CMR lookup fails.

## NASADEM

`NASADEM_HGT` version 001, provider LPCLOUD, concept `C2763264762-LPCLOUD`, DOI 10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001. 1 arc-second, 1x1 degree tiles, each a zip of about 13.7 MB. Static DEM (SRTM-derived). Only tiles overlapping the AOI are selected (`tiles_for_aoi`); a tile edge exactly on an integer degree does not pull in the neighbour.

## GPM IMERG

`GPM_3IMERGDF` version 07: Final Run, daily, 0.1 degree, GES_DISC, concept `C2723754864-GES_DISC`; the catalog temporal extent was 1998-01-01 to 2025-09-30 at the time of check. `GPM_3IMERGHH` 07 (half-hourly) and `GPM_3IMERGM` 07 (monthly) exist in CMR; only the provider mapping for these was tested, with mocks.

Limits (also attached to every record):

- Not real-time: Final Run latency is about 3.5 months.
- About 0.1 degree (roughly 10 km) grid. It does not represent point or slope-scale rainfall.
- One global file per day. AOI subsetting is a later-phase step. The size of a daily global file was not measured.

## SMAP (optional, off by default)

Default `SPL3SMP_E` v006 (9 km, concept `C2938664763-NSIDC_CPRD`). Others exist with different resolution/availability: `SPL3SMP` 009 (36 km), `SPL3SMAP` 003, `SPL3SMA` 003 (3 km radar; radar failed in 2015, so coverage is limited). Choose with `SMAP_COLLECTION`; resolution and valid dates come from the catalog.

## NASA Global Landslide Catalog

- Page: https://data.nasa.gov/dataset/global-landslide-catalog-export
- CSV: https://data.nasa.gov/docs/legacy/Global_Landslide_Catalog_Export/Global_Landslide_Catalog_Export_rows.csv
- A one-time export, current as of **2016-03-07**. **Not complete, not current; absence of an event proves nothing.** Use as historical reference only.
- Columns: `source_name, source_link, event_id, event_date, event_time, event_title, event_description, location_description, location_accuracy, landslide_category, landslide_trigger, landslide_size, landslide_setting, fatality_count, injury_count, storm_name, photo_link, notes, ..., country_name, country_code, admin_division_name, ..., longitude, latitude`.
- Required for import: `event_id`, `latitude`, `longitude`. Rows with missing/non-numeric/out-of-range coordinates, a duplicate `event_id`, or exactly (0, 0) are rejected as missing locations.
- Dates observed as `MM/DD/YYYY hh:mm:ss AM`. **Day/month order is assumed MM/DD (read as UTC); confirm on the first real import.** Unparseable dates are stored as NULL and counted.
- Mapping: `location_description` (else `event_title`) -> `location_name`; `landslide_category` -> `landslide_type`; `landslide_trigger` -> `trigger`; `country_name` -> `country`; whole row kept in `original_attributes`.
- Stored as collection `NASA_GLOBAL_LANDSLIDE_CATALOG_EXPORT`, version `export-2016-03-07`. The CSV and a `.sha256` sidecar are saved under `data/raw/landslide_catalog/`.
