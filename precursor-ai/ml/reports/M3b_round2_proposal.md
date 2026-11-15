# M3b / round 2 download PROPOSAL (nothing downloaded)

Date: 2026-11-15. Requested by the user at the M3 decisions: fill the missing static factors (distance to rivers, Quaternary faults, soil properties, NDVI) for the three B1 windows only, plus roads as a **reporting-bias diagnostic for M5 only (never a model feature)**. Not in round 2: SMAP, daily IMERG, SAR/InSAR (trigger model, deferred). All sizes below were obtained without downloading data: HTTP HEAD requests, CMR catalog metadata (`granule_size`, which is in MiB), and a 3.5 kB ranged read of one SoilGrids VRT header. Limits to respect: 30 GB project total, 2 GB per file, >= 15 GB free disk after downloads.

## 1. Summary
| # | Item | Source | Licence (as understood, text NOT_VERIFIED) | Login | Files | Size |
|---|---|---|---|---|---|---|
| 1 | Distance to rivers: HydroRIVERS v10, North America | hydrosheds.org | HydroSHEDS licence: free use with attribution | no | 1 | **66,335,898 B** (HEAD) |
| 2 | USGS Quaternary Faults | earthquake.usgs.gov | U.S. public domain (USGS) | no | 1 | **32,371,696 B** (HEAD) |
| 3 | Soil: SoilGrids 2.0, 5 properties x 3 depths (mean) | files.isric.org | CC BY 4.0 | no | 1 index VRT + <= 720 tiles | VRT **5,929,079 B** (HEAD) + tiles **<= 292,689,360 B** (48 tiles x 15 layers x 406,513 B, one tile measured by HEAD) |
| 4 | NDVI: VIIRS VNP13A3 v002 monthly 1 km, 2013-01..2017-12 | LP DAAC (LPCLOUD) | NASA open data | Earthdata (already working for LP DAAC) | 240 (4 tiles x 60 months) | **3,130.7 MiB = 3.283 GB** (CMR) |
| 5 | Roads (diagnostic only): OSM extracts, 4 files | download.geofabrik.de | ODbL 1.0 | no | 4 | **1,950,681,130 B** (HEAD; 655.9 + 673.2 + 255.6 + 366.0 MB) |
| | **Round 2 total** | | | | at most 967 files | **about 5.63 GB** (3.68 GB without roads) |
Total with roads: 66.3 + 32.4 + 5.9 + 292.7 (upper bound) + 3,282.7 + 1,950.7 = **5,630 MB (5.63 GB)**; without roads 3.68 GB. Project total after round 2: 4.58 GB (M2) + 0.01 (labels) + 5.63 = **about 10.2 GB** (limit 30). Largest single file: 673 MB (SoCal PBF) (limit 2 GB). Free disk today 52 GB, so about 46 GB would remain (limit 15 GB). Round 2 is within every limit.

## 2. Item details
### 2.1 Distance to rivers: HydroRIVERS v10 (North America)
- URL: https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_na_shp.zip (alternative geodatabase `HydroRIVERS_v10_na.gdb.zip`, 72,435,527 B, not needed).
- Role: feature `dist_river` (distance from each 5 km cell centre to the nearest river, with optional stream-size threshold from the attributes `UPLAND_SKM` / `DIS_AV_CMS`, to be chosen in M3b before looking at labels); also literature-supported (Prompts.md table: distance to river was among the most influential factors under extreme rainfall).
- Why not NHDPlus HR: more detailed but delivered per HUC4 geodatabase (hundreds of MB to GB each; the three windows would need dozens, well above 10 GB); at a 5 km analysis cell the extra detail does not pay.
- Limits: derived from the 15 arc-second HydroSHEDS DEM (about 500 m positional accuracy) which is fine for 5-10 km cells but not for slope-scale hydrology; stream-size threshold and the minimum catchment of included rivers NOT_VERIFIED; contents not opened.

### 2.2 USGS Quaternary Faults
- URL: https://earthquake.usgs.gov/static/lfs/nshm/qfaults/Qfaults_GIS.zip (Last-Modified 2026-02-23).
- Role: feature `dist_fault` (distance to the nearest mapped Quaternary fault trace; optionally restricted to young/active classes, rule fixed in M3b before using labels). Covers CA, OR, WA.
- Limits: mapped traces are incomplete and uneven (offshore, forested terrain, Cascadia); layer names, attribute fields and age classes NOT_VERIFIED (file not opened); distance to a fault is an indirect proxy.

### 2.3 Soil: SoilGrids 2.0 (ISRIC), selected properties
- Index: https://files.isric.org/soilgrids/latest/data/clay/clay_0-5cm_mean.vrt (5.9 MB, 159,246 x 58,034 px, 250 m, Interrupted Goode Homolosine, Int16, nodata -32768, tiles 450 x 450 px). The tile list is identical for every layer, so ONE VRT is read to enumerate tiles; the other layers' tiles are fetched directly by the same relative path (`<prop>/<prop>_<depth>_mean/tileSG-xxx-yyy/tileSG-xxx-yyy_a-b.tif`).
- Layers (15): properties `clay`, `sand`, `silt` (texture), `bdod` (bulk density), `cfvo` (coarse fragments) x depths `0-5cm`, `5-15cm`, `15-30cm`, statistic `mean` only. Rationale: texture, bulk density and coarse-fragment content control permeability and shear strength; deeper than 30 cm and uncertainty statistics are not requested. (Organic carbon, pH and water content are left out.)
- Access / clipping: the tiles are plain striped GeoTIFFs of 406,513 B each (measured on `clay_0-5cm_mean/tileSG-018-027/tileSG-018-027_2-4.tif`), not cloud-optimised mosaics, so "clip by COG range read" reduces to fetching only the tiles that touch each window. Tiles per window, computed from the window boxes projected into the VRT grid: OR_WA 4 x 3 = 12, CA_N 5 x 4 = 20, CA_S 4 x 4 = 16, **at most 48 tiles per layer** (fewer if ocean tiles do not exist) = at most 720 files, **<= 292,689,360 B**. The exact count is fixed when the VRT is read (that read, 5.9 MB, is the only metadata transfer and is included above).
- Limits: modelled (machine-learning) predictions, not measurements; large uncertainty in data-sparse regions, mountains and forests; coarse 250 m, then aggregated to 5 km; layer-to-file naming assumed from one VRT (tile paths of the other 14 layers NOT_VERIFIED until the first fetch; stop if any 404).

### 2.4 NDVI / vegetation: VIIRS VNP13A3 v002 (monthly, 1 km, sinusoidal grid)
- Collection `VNP13A3` v002, concept `C2631828309-LPCLOUD`, first month 2012-01; files `VNP13A3.A<YYYYDDD>.<tile>.002.<proc>.h5` (HDF5).
- **Years: 2013-01 .. 2017-12 (60 months, 5 full calendar years)**; the long-term mean NDVI is the mean of the valid monthly values over those 60 months, plus a peak-season (July-August) mean and a winter (January-February) mean and a seasonal amplitude, defined in M3b. Tiles: h09v04, h08v04, h08v05, h07v05 (the tiles that intersect the three windows; tile list from the CMR bounding-box query for the same month).
- Size (CMR sums, MiB): h09v04 1,309.1; h08v04 262.1; h08v05 1,473.7; h07v05 85.8; total **3,130.7 MiB** for 240 granules; largest granule 25.0 MiB.
- Why this product: it is delivered as HDF5, which the GDAL installed in the ML environment can read (it has no HDF4 driver; verified by listing the drivers: HDF5 and netCDF present, HDF4 absent), so no new dependency is needed.
- **Alternative B (not proposed unless you prefer it):** MODIS Terra MOD13A3 v061, 2001-2017 (17 years, a real long-term record; 816 granules, **7,485.8 MiB = 7.85 GB**), but it is HDF4-EOS, which needs a new reader package or a GDAL build with HDF4. That dependency would have to be listed, justified and approved first.
- Limits: only 5 years, all after 2012, so it overlaps only the 2014-2017 events (335 of 667 strict events) and misses the heavy 2010-2011 winters; land cover (2021) and NDVI therefore describe the landscape after most events, a **temporal mismatch** to be reported in M5; vegetation changes after fires and logging are not captured; the sinusoidal geolocation of the HDF5 SDS, the SDS name for NDVI and the quality/pixel-reliability layer are NOT_VERIFIED (the HDF5 driver may not georeference the sinusoidal grid; the standard MODIS tile grid arithmetic would then be applied and checked). **Step 0 of the download: fetch ONE file (about 25 MB) and verify layout and georeferencing before fetching the other 239; stop if it cannot be read.**

### 2.5 Roads, reporting-bias diagnostic only
- Geofabrik OpenStreetMap extracts (all HEAD 200 after a 307 redirect to the mirror, data dated 2026-11-14): `north-america/us/california/norcal-latest.osm.pbf` 655,919,523 B; `.../california/socal-latest.osm.pbf` 673,156,133 B; `.../us/oregon-latest.osm.pbf` 255,643,879 B; `.../us/washington-latest.osm.pbf` 365,961,595 B. Total 1,950,681,130 B; each file below 2 GB. They cover the windows: NorCal for CA_N (37-40 N), SoCal for CA_S (32-35 N), Oregon plus Washington for OR_WA.
- Use: M5 only, to test whether GLC events concentrate near roads/populated places (inventory reporting bias: the GLC is news-derived). Distance to roads is **not** a model feature; it will not enter M6 feature lists or any model. Licence ODbL 1.0 (attribution and share-alike apply to derived databases; the diagnostic is internal).
- Lighter option: skip this item (saves 1.95 GB); the bias diagnostic can then only use the already available land-cover built-up share.
- Limits: OSM completeness varies and changed over 1997-2017 (a 2026 snapshot of roads vs 1997-2017 events); extracts include the whole subregion, not only the window; the OSM reader in GDAL (available in pyogrio) is slow on 650 MB files but workable.

## 3. Proposed procedure (if approved)
1. Pre-check: free disk >= 15 GB after the planned total; record real sizes again from the response headers.
2. NDVI step 0: one VNP13A3 file, verify HDF5 layout, NDVI SDS, quality layer, sinusoidal georeferencing; then the rest in batches with resumable downloads through the Phase 2 manager (Earthdata login from `.env`, never printed).
3. Other items by plain HTTPS with SHA-256 per file; stop on any size deviation above 1%, any 4xx, or any block page (Cloudflare etc.); no circumvention.
4. Record URL, licence, retrieval date, size and SHA-256 per file in the raw manifest and DATASET_LOG; integrity checks; one report `ml/reports/M2b_acquisition.md`.
5. Then M3b: derive the new factors on the same 5 km grid (and the 10 km sensitivity grid): `dist_river`, `dist_fault`, soil layers (mean over 0-30 cm weighted by depth thickness, plus the three single depths if useful), NDVI statistics; road diagnostics kept separate from the factor tables. Re-run M3 end to end with a new manifest. Only then M4.

## 4. What was not verified
Contents and layer names of the HydroRIVERS and Qfaults zips; licence texts (understood from the providers' general policies); the other 14 SoilGrids layers' tile paths and the existence of ocean tiles; NDVI SDS names, quality layer and HDF5 georeferencing; whether the 4 NDVI tiles are the complete intersection set (taken from the CMR bounding-box query); OSM subregion boundaries versus the window edges (assumed from the region names; the Geofabrik index was not read).

## 5. Decisions needed from you
1. Approve items 1-5 as listed, or remove items (roads: 1.95 GB, optional).
2. NDVI: option A (VIIRS 2013-2017, 3.28 GB, no new dependency) or option B (MODIS 2001-2017, 7.85 GB, needs an HDF4 reader dependency to be approved)?
3. SoilGrids property/depth list as proposed (clay, sand, silt, bdod, cfvo; 0-5, 5-15, 15-30 cm, mean)?
No download is made until you approve.
