# M5b: label-source proposal (STOP for your approval)

Date: 2026-11-15. Status: **PROPOSAL. Nothing downloaded.** Only HEAD requests, page reads and count-only map-service queries were made (one host at a time, no login, no token, no workaround of blocked sites). Every unconfirmed item is `NOT_VERIFIED`. Probe code: [m5b_inventory_probe.py](../scripts/m5b_inventory_probe.py) (standard library, count-only); raw output: `ml/reports/m5b_probe/inventory_probe.json`. M6 is not started.

## 0. Why, and the plain warnings
M5 found that GLC labels track where landslides get **reported** (built-up share AUC 0.82), not slope. Mapped inventories (lidar and field/aerial mapping by geological surveys) are a different label process and may reduce, not remove, that bias. Read these first:

1. **Mapped inventories are mostly UNDATED deposits and scarps.** Fine for a static susceptibility ranking; useless for a trigger task (already deferred) and for any temporal hold-out. They **mix prehistoric and recent slides**; some sources give only relative age classes (SLIDO `AGE`, CGS `activity`), WA and USGS dates are NOT_VERIFIED per window.
2. **Coverage is uneven.** "No polygon" is not "no landslide" outside the mapped areas (lidar surveys cover only part of each state). A **mapped-area mask is required**, or absence stays pseudo-absence of unknown quality. No source below is confirmed to ship such a mask (details per source). Without a mask, the new labels would simply replace one reporting bias with a mapping-effort bias.
3. **California: no bulk file was found.** Options: extract from the CGS ArcGIS services (terms NOT_VERIFIED) or take California from the USGS compilation.
4. **Three states = three protocols** (Oregon SLIDO, Washington DNR/DOGAMI SP-42, California CGS): different landslide types, confidence scales, polygon vs point conventions. Harmonisation into one documented label definition is required (as was done for lithology). The USGS compilation does part of this (uniform `Confidence`, `LS_Type`, dates) but its own metadata says the confidence "does not reflect a formal accuracy assessment" and the classification of the originals is often unknown.
5. The counts below are **map-service feature counts intersecting the window rectangle** (several layers hold the same slide as point, line and polygon, and polygons may be partly outside). They are NOT numbers of distinct landslides and NOT numbers of positive cells. Positive-cell counts need a download and a mask; NOT_VERIFIED.

Limits you set: 30 GB total downloads (about 8 GB raw so far), 2 GB per file, at least 15 GB free after downloads (57 GB free now, measured with `df`). All candidate files are far below these (section 6).

## 1. Source 1: USGS "Landslide Inventories across the United States", v3.0 (Feb 2025)
- **URL:** https://www.usgs.gov/data/landslide-inventories-across-united-states-ver-30-february-2025 ; catalog page https://data.usgs.gov/datacatalog/data/USGS:671eef1fd34ed0f827ea9f12 (HTTP 200, read) ; metadata XML https://data.usgs.gov/datacatalog/metadata/USGS.671eef1fd34ed0f827ea9f12.xml (HTTP 200, read). **DOI https://doi.org/10.5066/P14AJF8I** (VERIFIED in the catalog page text, citation Belair, Mirus, Luna and Jones, 2019, ver. 3.0, Feb 2025).
- **Licence:** catalog page shows "Access public", **License: http://www.usa.gov/publicdomain/label/1.0/ (US public domain label)**; metadata XML: access and use constraints "none", fees "None". Read from the provider page, not independently checked in a legal sense; the constituent inventories (non-USGS authors) may carry their own terms: **NOT_VERIFIED**. The data release asks users to cite the constituent inventories too.
- **Size:** **NOT_VERIFIED.** The file list and sizes are not on the catalog page text; ScienceBase (`sciencebase.gov/catalog/item/...`) answered **HTTP 403** to a plain request (blocked, not circumvented). Files named in the abstract: `US_Landslide_v3_gpkg`, `_shp`, `_csv`, an ancillary database, `us_ls_v3_references.csv`, `us_ls_v3_changes.txt`, a spreadsheet.
- **Format / access:** GeoPackage, shapefile, CSV (points and polygons; points are polygon centroids in `Lat_N`, `Lon_W`). Access path to the bytes is the open problem: via ScienceBase (403 to scripts). Possible honest routes: you download the file in a browser and place it in `data/ml/raw/` (then I hash and use it), or you approve a specific direct link once I find one by page read.
- **Coverage:** 55 inventories nationwide. **Which inventories cover which window, and whether SLIDO, WA and CGS are included: NOT_VERIFIED** (the `Inventory` field and `us_ls_v3_references.csv` would show it; the catalog text read does not list them). Overlap with the GLC (the old Source of our labels) is possible (earlier USGS compilations used COOLR/GLC-type records): NOT_VERIFIED.
- **Geometry:** points and polygons in one schema; `Confidence` class; `LS_Type`.
- **Positional accuracy:** only through the `Confidence` class (it "reflects the resolution and quality of input data and the method"); no metres. NOT_VERIFIED per inventory.
- **Dates:** `Date_Min` / `Date_Max` (machine-readable; empty `Date_Max` = day-exact), but many mapped entries are expected to be undated (NOT_VERIFIED how many in our windows).
- **Positives per window:** NOT_VERIFIED (needs the file).
- **Mapped-area mask:** none described in the catalog text. A crude mask could be derived from each `Inventory`'s extent; that is weak (NOT_VERIFIED).
- **Effect on labels:** one harmonised schema for all three states; includes non-landslide entries on purpose ("gullies", "avalanche chutes"), to be filtered by `LS_Type`/`Confidence`.

## 2. Source 2: Oregon DOGAMI SLIDO 4.5
- **URL:** https://pubs.oregon.gov/dogami/SLIDO/4.5/SLIDO_Release_4p5_wMetadata.gdb.zip. **HEAD re-measured today: HTTP 200, 598,643,575 B (0.60 GB), Last-Modified 2024-04-12.** Page mentions SLIDO-4.6; no 4.6 link found. Map service: https://gis.dogami.oregon.gov/arcgis/rest/services/Public/SLIDO42/MapServer (version 4.2 service; queried count-only).
- **Licence: NOT_VERIFIED.** The SLIDO disclaimer page (read) is only a no-warranty / not-for-site-specific-planning notice; no licence or reuse statement found.
- **Format / access:** Esri file geodatabase in a zip, plain HTTPS GET, no login. Reading needs GDAL's OpenFileGDB driver (rasterio/fiona/pyogrio in `ml/.venv` availability NOT_VERIFIED; a new dependency would be listed for approval first).
- **Coverage:** Oregon only. Window OR_WA is (-124,45,-121,48): Washington part is **not** covered by SLIDO; the Oregon part is the strip about 45-46.3 N.
- **Geometry:** historic landslide **points** (year/date fields `YEAR`, `DATE_RANGE`, `MONTH`, `DAY`; report-based, same bias family as GLC), **deposit polygons** (`AGE`, `CONFIDENCE`, `MOVE_CLASS`), **scarp lines and head-scarp polygons**. Map-scale / lidar mapping differs by source map (`REF_ID_COD`, `LOC_METHOD`).
- **Positional accuracy:** by `LOC_METHOD` and source map; metres NOT_VERIFIED.
- **Dates:** points: dated (YEAR, some MONTH/DAY, many undated NOT_VERIFIED); deposits: relative `AGE` classes, not dates.
- **Count-only query, window rectangle OR_WA (service SLIDO42, features intersecting the rectangle; includes Oregon only):** historic points **6,501**; deposits **27,408**; head scarps **14,918**; scarps **22,621**. These are feature counts, overlapping representations, not distinct landslides.
- **Mapped-area mask:** the SLIDO "inventory map index" (polygons of the source maps) is the natural mask. **Whether it ships in the gdb or the service: NOT_VERIFIED** (layer list probed only for the four feature layers above).

## 3. Source 3: Washington DNR / Washington Geological Survey Landslide Inventory Database
- **URL:** https://fortress.wa.gov/dnr/geologydata/publications/data_download/ger_portal_landslide_database.zip. **HEAD re-measured today: HTTP 200, 908,587,865 B (0.91 GB), Last-Modified 2026-04-02.** Digital Data Series 29 v1.4 (April 2025, from your reading).
- **Licence: NOT_VERIFIED** (your reading: provided "as is", non-regulatory; no reuse licence read).
- **Format / access:** zip over HTTPS, no login; internal format (gdb/shp) NOT_VERIFIED. ArcGIS services `Public_Geology/Landslide_Inventory_Database/MapServer` and `Hosted/Landslides_Offline/FeatureServer` both answered **HTTP-level error 499 "Token Required"**: blocked, not circumvented, no counts.
- **Coverage:** Washington only; **which counties/areas are mapped: NOT_VERIFIED** (lidar-based mapping by SP-42 protocol plus compiled older sources, per your reading). OR_WA window Washington part is (-124..-121, 45..48 N) Washington portion about 45.5-48 N.
- **Geometry:** polygons expected (deposits/scarps); point/polygon split and positional accuracy NOT_VERIFIED. Lidar-mapped polygons are likely more accurate than GLC (about 5 km), as a hypothesis only.
- **Dates:** likely undated or relative age; NOT_VERIFIED.
- **Positives per window:** NOT_VERIFIED (service blocked; the zip must be opened).
- **Mapped-area mask:** lidar/mapping coverage index NOT_VERIFIED; likely needed and possibly a separate WGS layer.

## 4. Source 4: California Geological Survey (CGS) Landslide Inventory
- **URL:** services `https://gis.conservation.ca.gov/server/rest/services/CGS/LandslideInventory_{DC1_Younger,DC1_Older,DC2,DC3}/MapServer` (HTTP 200, queried count-only). Metadata page https://maps.conservation.ca.gov/cgs/metadata/CaLSI_metadata.html: **re-fetch today returned HTTP 403**; from your earlier reading: data must be obtained from CGS, copyright notice and citation rules. **No bulk file found.**
- **Licence / extraction terms: NOT_VERIFIED.** Service copyright text: "California Geological Survey, California Department of Conservation". Paging through a map service to extract features is a "service extraction"; I will not do it without your written confirmation that the terms allow it (or CGS permission).
- **Size:** unknown; extraction would be thousands of features per window (sections below), small in bytes (expected well under 1 GB; NOT_VERIFIED).
- **Format / access:** ArcGIS REST query (JSON/GeoJSON), no login for count queries; feature extraction not attempted.
- **Coverage:** California statewide in tiers DC1 (younger, older), DC2, DC3. **What the "DC" tiers mean (data collection / mapping tiers?) is NOT_VERIFIED**; they appear to be mapped in different projects, so coverage is uneven and the footprint of each tier is itself the mapped-area mask (candidate mask: tier footprints, NOT_VERIFIED).
- **Geometry:** points, lines, polygons (deposit, source/scarp, single feature, "questionable" classes).
- **Positional accuracy:** `confidence` field and `base_map`, `map_year`; metres NOT_VERIFIED.
- **Dates:** `map_year`, `activity` (active/historic/dormant-young/older classes) and creation/revision dates (those are database dates, not event dates). Slide dates NOT_VERIFIED; not event-dated.
- **Count-only queries, features intersecting the window rectangle (overlapping layer representations; NOT distinct landslides):**

| Service (layer) | CA_N | CA_S |
|---|---|---|
| DC1_Younger, single-feature polygons | 3,740 | 4,934 |
| DC1_Younger, deposit polygons | 811 | 391 |
| DC1_Younger, single-feature points / source points | 30 / 168 | 40 / 0 |
| DC1_Older, single-feature polygons | 2,438 | 10,875 |
| DC1_Older, deposit polygons | 507 | 121 |
| DC2, deposit polygons (+ questionable) | 10,874 (+1,096) | 640 (+0) |
| DC2, single-feature polygons (+ questionable) | 2,327 (+30) | 1,043 (+423) |
| DC2, source/scarp polygons | 2,901 | 226 |
| DC3, deposit polygons (+ questionable) | 2,621 (+942) | 0 |
| DC3, single-feature polygons (+ questionable) | 1,562 (+1,313) | 1 |
Layer-by-layer counts are in the JSON. The "Reported Landslide Events" point service was not probed (report-based, same bias problem as GLC).

## 5. Optional bias covariate: GHSL GHS-POP R2023A, epoch 2015, 1 km (diagnostic only)
- **URL:** https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/GHS_POP_E2015_GLOBE_R2023A_54009_1000/V1-0/GHS_POP_E2015_GLOBE_R2023A_54009_1000_V1_0.zip. **HEAD measured today: HTTP 200, 320,436,226 B (0.32 GB), Last-Modified 2024-09-24.**
- **Licence:** CC BY 4.0 per one secondary source: **NOT_VERIFIED** against the JRC page.
- **Format:** GeoTIFF in a zip, 1 km Mollweide (ESRI:54009), global single file; a per-tile option is NOT_VERIFIED (so 0.32 GB for the global file).
- **Use:** model B / bias-matched background (A-matched) stratification and reporting-bias diagnostics. It is **not** a label source and not a susceptibility feature. Built-up share from WorldCover (already held) can already build the A-matched strata, so the covariate is **optional**: it adds an independent population measure (built-up share is also a feature of land cover from a different source).

## 6. Storage check (nothing downloaded)
| Item | Size | How measured |
|---|---|---|
| SLIDO 4.5 zip | 0.60 GB | HEAD today |
| WA DNR zip | 0.91 GB | HEAD today |
| USGS v3.0 | NOT_VERIFIED | blocked / not listed |
| CGS | NOT_VERIFIED, small | service extraction only |
| GHS-POP 2015 | 0.32 GB | HEAD today |
Worst case for the three measured files: 1.83 GB compressed (file geodatabases typically unpack 2-5x; unpacked size NOT_VERIFIED, up to about 9 GB at 5x). Total after downloads about 8 + 2 to 11 = at most about 19 GB (limit 30 GB); each file < 2 GB (limit met); free disk 57 GB now, at least 46 GB after (limit 15 GB). USGS v3 size must be measured before approval.

## 7. How the new labels change the study, and the sealed hold-out
- **Label meaning changes** from "a reported slide point" to "a mapped landslide feature (polygon or point), any age". Positive-cell definition (cell intersects a mapped polygon of accepted type/confidence, or polygon-area share) is decided in M6 and fixed before models.
- **Hold-out rule (your decision 6):** keep the same 50 km block geometry and the sealed block assignment (`m5_provisional_holdout_v1`, seal `1d4a6741...`). **Before any exploration of the new labels**, assign every new feature to the existing blocks by its centroid or, for polygons, by intersection: a feature touching a held-out block or its 10 km gap is kept out of training (held-out, or gap if it also touches training blocks); the cell-level gap is re-derived from cell footprints in M6. Held-out blocks stay held out. The re-assignment table is hashed and added to the seal record before any exploration; the held-out part of the new labels is never opened, plotted or summarised.
- **Known consequence:** the GLC events remain in the sealed event split. The new labels are a **second label set** for the same blocks, so comparisons GLC-labels vs mapped-labels on the same training blocks and the same held-out blocks are possible (M7/M8), which also shows how much of the skill is label-process dependent.
- **Mask needed first:** M6 cannot define "background" from unmapped cells without a mapped-area mask; if none can be built for a source, that source supports only a "mapped-area-only" analysis (restricted to the mask) or a bias-matched comparison.
- **"Not supported by these labels"** stays an acceptable M7/M8 outcome.

## 8. Options, ranked
| Rank | Option | Pros | Cons / unknowns |
|---|---|---|---|
| 1 (recommended) | **USGS v3.0 compilation for all three windows** (one file, one schema, public-domain label, `Confidence`, `Date_Min/Max`, `Inv_URL`) | single harmonised schema, no per-state scraping, licence label read, one cite | Size and inventory list NOT_VERIFIED; ScienceBase 403 to scripts (needs your browser download or a direct link I can verify); confidence is not accuracy; no mask; overlap with GLC NOT_VERIFIED; constituent terms NOT_VERIFIED |
| 2 (fallback if 1 is unobtainable) | **SLIDO 4.5 + WA DNR zips (OR_WA, 1.5 GB) + CGS only after terms confirmed** | bulk, direct HTTPS for OR/WA, official and more detailed (polygons, ages) | three protocols; licences NOT_VERIFIED; CGS terms and extraction unclear; WA service token-blocked, WA mapped area unknown |
| 3 | **OR_WA only (SLIDO + WA), keep GLC for California** | smallest, no California legal question | two label processes across windows; leave-one-window-out becomes confounded with label source |
| 4 | **Keep GLC only**, add bias-matched background (A-matched) and optional GHS-POP | no download except 0.32 GB, no new protocols | labels remain report-driven; the A-matched control only partly corrects it |
Recommended: **option 1**, first as a **size and file-list check only** (no download), then your approval of the exact file(s). If the file cannot be fetched by an approved route, ask you to download the GeoPackage in a browser. Option 4's A-matched run is already approved and needs no new data (GHS-POP is optional on top).

## 9. Decisions needed from you
1. Choose the label option (1, 2, 3 or 4) or reject new labels. If 1: approve that I (a) read the file list and sizes of the USGS v3.0 release through the catalog or DOI, HEAD requests only, and (b) if my script gets 403 from ScienceBase, you download the GeoPackage yourself into `data/ml/raw/` (I will not bypass the block).
2. If 2 or 3: approve the exact files (SLIDO 4.5 zip, 598,643,575 B; WA DNR zip, 908,587,865 B). For California, either confirm CGS permits service extraction (state the terms or contact result) or choose the USGS compilation for California.
3. Licences: accept using SLIDO, WA and CGS data for this research under their disclaimers/terms even though a licence is NOT_VERIFIED, or ask me to request the terms first.
4. Approve the mapped-area-mask requirement (no background from unmapped areas) and the hold-out re-assignment rule in section 7.
5. GHS-POP 2015 (0.32 GB): approve (optional) or skip.
6. Approve that M6 may define positive cells from mapped polygons, with GLC kept as a comparison label set.
