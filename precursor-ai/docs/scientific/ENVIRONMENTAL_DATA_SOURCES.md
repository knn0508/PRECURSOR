# Environmental data sources (Phase 4, soil / land cover / seismic)

Status labels: IMPLEMENTED_AND_TESTED | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | PARTIALLY_IMPLEMENTED | PLACEHOLDER | BLOCKED.
Verified = read from the official page named below. Assumed = not stated by an official page we fetched.
No provider in this phase downloads datasets. Providers produce a PROPOSAL, list files the user placed in
`data/external/<provider>/`, and process those. All tests use synthetic fixtures and fake HTTP sessions; no real file has been processed
(`REAL_DATA_VALIDATION: NOT_PERFORMED`).

## USGS Earthquake Catalog (FDSN event API)
- Official: https://earthquake.usgs.gov/fdsnws/event/1/ ; GeoJSON format: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
- Verified: params `starttime, endtime, minlatitude, maxlatitude, minlongitude, maxlongitude, minmagnitude, limit (1-20000), offset (default 1), orderby (time, time-asc, magnitude, magnitude-asc), format=geojson`; more than 20000 results returns HTTP 400; methods `query` and `count`; GeoJSON properties `mag, place, time, updated, url, detail, status, magType, type, net, ids, code, sources, types ...`; geometry Point `[lon, lat, depth]`.
- Licence/credit: USGS-authored data are U.S. public domain; USGS asks for credit ("U.S. Geological Survey") - https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits. The API page itself states no attribution text.
- Assumed (not stated on the fetched pages): `time` is epoch milliseconds UTC and depth is km (common USGS usage); there is no documented numeric rate limit (the page only recommends the real-time feeds for automated applications); whether `offset` may exceed 20000.
- Implementation: `fetch(bbox, start, end, min_magnitude, session)` does read-only paginated GETs (page size <= 20000, `orderby=time-asc`, stops on a short page), retries 429/5xx/transport errors with bounded backoff (honours numeric Retry-After), treats HTTP 400 as non-retryable (error on first page; on a later page, keeps results and warns "truncated"), caps total records (default 50000, warns), skips malformed features with warnings, de-duplicates by id. No time-window splitting; antimeridian AOIs rejected.
- Limitations: catalog completeness varies by region and magnitude; magnitudes of different `magType` are not strictly comparable; earthquakes are independent observations, no causal link to landslides is implied.
- Status: **IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA** (fetch tested only with a fake session; the one provider that can touch the network).

## SoilGrids 250 m v2.0 (ISRIC)
- Official: https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs.html , https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html
- Verified: 250 m, six depth intervals 0-5, 5-15, 15-30, 30-60, 60-100, 100-200 cm; statistics Q0.05, Q0.50, mean, Q0.95, uncertainty (= (Q0.95-Q0.05)/Q0.50, x10, stored as integer); property table with mapped units and factor (divide stored integer by factor): bdod cg/cm3 /100 -> kg/dm3; cec mmol(c)/kg /10 -> cmol(c)/kg; cfvo vol permille /10 -> vol%; clay, sand, silt g/kg /10 -> %; nitrogen cg/kg /100 -> g/kg; ocd hg/m3 /10 -> kg/m3; ocs t/ha /10 -> kg/m2; phh2o pH x10 /10 -> pH; soc dg/kg /10 -> g/kg; wv0010/wv0033/wv1500 /10 -> %. Citation: Poggio et al. (2021), SOIL 7, 217-240. Licence CC BY 4.0 (via ISRIC search snippets/metadata, not a fetched licence page). Access routes listed by ISRIC: WebDAV (VRT), WCS, Google Earth Engine, R.
- NOT verified: native CRS (Interrupted Goode Homolosine is expected, but the code never assumes it: it transforms the AOI into the CRS stored in each file); nodata value (the file's own nodata is used; none declared means all pixels count as valid and a warning is emitted); REST `rest.isric.org` rate limit (~5 calls/min is unverified; no REST client is implemented); the WCS endpoint URLs and file naming (the reader expects `<property>_<top>-<bottom>cm_<statistic>.tif`, an assumption).
- Conversion: only `raw / documented factor`; raw and converted statistics and units are both kept.
- Limitations: modelled (machine-learning) predictions, not measurements; uncertainty is large in data-sparse regions; not a susceptibility input by itself.
- Status: **IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA** (proposal + local GeoTIFF reader; statistics and clipped maps; not a download integration).

## Land cover: ESA WorldCover (chosen) vs MODIS MCD12Q1 (alternative, not implemented)
- Official: https://esa-worldcover.org/en/data-access ; legend/colours (v200) from the Earth Engine catalogue page https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200
- Choice: WorldCover. 10 m versus 500 m (a landslide-scale AOI of a few km holds thousands of pixels versus tens), global, public AWS Open Data bucket readable with no credentials (`--no-sign-request`), CC BY 4.0. MCD12Q1 is annual (long record) but 500 m and requires an Earthdata login; it remains an alternative (not verified here, not implemented).
- Verified: v100 = 2020, v200 = 2021; 3x3 degree COG tiles in EPSG:4326 (2,651 tiles); `s3://esa-worldcover/v200/2021/map`, `s3://esa-worldcover/v100/2020/map` (eu-central-1); Terrascope needs login; CC BY 4.0; 11 classes: 10 Tree cover #006400, 20 Shrubland #ffbb22, 30 Grassland #ffff4c, 40 Cropland #f096ff, 50 Built-up #fa0000, 60 Bare / sparse vegetation #b4b4b4, 70 Snow and ice #f0f0f0, 80 Permanent water bodies #0064c8, 90 Herbaceous wetland #0096a0, 95 Mangroves #00cf75, 100 Moss and lichen #fae6a0. The legend page of v100 was not fetched separately (assumed identical class codes).
- NOT verified: nodata value of the Map layer (the file's own nodata is used), tile file naming, tile sizes (proposal assumes ~150 MB per tile, labelled ESTIMATE).
- Method: native-pixel window read (no resampling, so class ids are never averaged); percentages are of valid AOI pixels; ids outside the legend are reported separately, never dropped; no risk labels. The window is the AOI bounding box and cells outside the polygon are masked.
- Limitations: classified product with its own accuracy (not assessed here); single-year snapshot; 2020 and 2021 versions use different algorithm versions and should not be differenced as change.
- Status: **IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA**.

## Addendum datasets (documented in their own files)
- SMAP SPL3SMP_E soil moisture: [SMAP_METHODOLOGY](SMAP_METHODOLOGY.md) (verified from NSIDC user guides; HDF5 attribute names UNKNOWN). Status IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA.
- Lithology, NDVI (user file / MODIS vegetation index) and distance to river/fault/road: [EXTERNAL_LAYERS](EXTERNAL_LAYERS.md); all user-placed, nothing downloaded. Status IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA.
- IMERG half-hourly (GPM_3IMERGHH V07, optional): [RAINFALL_METHODOLOGY](RAINFALL_METHODOLOGY.md); product and `precipitation` variable verified, file naming/time/grid/fill UNKNOWN.
- Common reference grid: [REFERENCE_GRID](REFERENCE_GRID.md). Soil and land cover now also write clipped map rasters (same file).

## Pointers (documented elsewhere)
- NASADEM, GPM IMERG: documented by the DEM/rainfall owners (see RAINFALL_METHODOLOGY.md); not covered here.
- NASA Global Landslide Catalog: Phase 2 (`landslide_catalog.py`); a one-time export current to 2016-03-07, incomplete, reporting-biased, not ground truth. `historical_event_features` always attaches this limitation, counts events with invalid coordinates/dates in `skipped`, and measures distance from the AOI centroid by haversine (mean Earth radius 6371.0088 km; error up to ~0.5% versus the ellipsoid).
