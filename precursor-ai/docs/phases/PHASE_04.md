# Phase 4: Environmental & Geospatial Data Integration

Status: **PARTIALLY_COMPLETED**: implemented and tested on **synthetic** data only. **No real NASADEM, IMERG, SoilGrids, WorldCover, USGS or catalog data has been processed**; nothing is `IMPLEMENTED_AND_TESTED`. Roadmap: [ROADMAP](../project/ROADMAP.md). Decisions: [ADR-0005](../adr/ADR-0005-environmental-integration-design.md), [ADR-0006](../adr/ADR-0006-stack-manifest-and-reference-grid.md) (manifest and reference grid, completion addendum). Test and Docker results: [PROJECT_STATUS](../project/PROJECT_STATUS.md).

## Objective and scope
A reusable layer that turns already-downloaded or locally placed source data into standardised environmental layers, descriptive features, provenance and quality reports per monitored area. **Out of scope:** acquisition (Phase 2), InSAR processing (Phase 3), computer vision (Phase 5), time-series forecasting (Phase 6), any ML, risk score, probability or prediction, and the full Phase 9 dashboard.

## Prerequisites
Phase 2 records and files (NASADEM tiles, GPM daily files), the Phase 2 landslide table, optional Phase 3 products, user-placed soil/land-cover files in `data/external/`. None of these exists with real data yet.

## Pipeline (stages)
`DEM -> TERRAIN -> RAINFALL -> SMAP -> SOIL -> LAND_COVER -> LITHOLOGY -> NDVI -> DISTANCES -> HISTORICAL_LANDSLIDES -> SEISMIC -> INSAR -> REFERENCE_GRID -> FEATURES -> MANIFEST -> QUALITY` (16 stages; the original ten were extended by the completion addendum). REFERENCE_GRID aligns every raster layer to one grid (natives kept; method in [REFERENCE_GRID](../scientific/REFERENCE_GRID.md)); MANIFEST writes the stack inventory. Each stage ends `DONE`, `PARTIAL`, `NOT_AVAILABLE` (no input: recorded with a reason, never zero-filled), `SKIPPED` (identical inputs already processed; reused) or `FAILED` (isolated: other stages continue). Run status: `COMPLETED` only if everything requested finished; `PARTIAL` if any dataset is missing, partial or failed; `FAILED` only if nothing usable was produced. Stages can be selected, retried and forced.

## Dataset status (honest)
| Dataset | Status | What exists |
|---|---|---|
| NASADEM elevation | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | Reads Phase 2 tiles (.zip/.hgt/.tif), mosaic with overlap and missing-tile handling, AOI clip |
| Slope / aspect | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | Horn method; metre cell sizes for geographic grids; aspect clockwise from north, flat = no-data; circular statistics |
| GPM IMERG V07 daily | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | AOI statistic, daily/monthly/rolling sums, missing days stay missing. **File layout, units and fill value unverified from official sources** |
| GPM IMERG half-hourly (optional, `rainfall_resolution=half_hourly`) | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | rate (mm/hr) x 0.5 h; a UTC day is observed only when all 48 intervals are present, otherwise missing (never scaled or interpolated). Product GPM_3IMERGHH V07 verified; file name pattern, 48-per-day, time epoch, grid and fill UNKNOWN |
| SMAP SPL3SMP_E soil moisture | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | AOI daily series, AM and PM separate, optional quality filter, missing days stay missing. Group/variable names verified from NSIDC user guides; HDF5 attribute names for units/fill UNKNOWN. [SMAP_METHODOLOGY](../scientific/SMAP_METHODOLOGY.md) |
| Lithology (user file) | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | class-id raster or GeoJSON polygons; class names only from the user's sidecar legend. [EXTERNAL_LAYERS](../scientific/EXTERNAL_LAYERS.md) |
| NDVI (user file / MODIS vegetation index) | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | scaling only when declared by the file or option; MOD13Q1 v061 facts verified, 1 km specifics assumed |
| Distance to river / fault / road (user GeoJSON) | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | Euclidean metres in the metric grid CRS; a missing kind is NOT_AVAILABLE for that kind and the stage PARTIAL |
| SoilGrids | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | Reads user-placed GeoTIFFs; statistics plus clipped native-grid maps (one layer per property/depth); download proposal only |
| Land cover (ESA WorldCover) | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | Class ids and official legend preserved; statistics plus clipped map raster (tiles merged only when grids match) |
| NASA Global Landslide Catalog | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | Reuses the Phase 2 table; empty until imported (reported as not available, not zero events) |
| USGS earthquakes | IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA | Explicit-action fetch with pagination/retry; tested with a fake HTTP session only |
| Phase 3 InSAR products | PARTIALLY_IMPLEMENTED | Referenced with provenance; only real-satellite products feed features; synthetic and unverified are labelled and excluded |

Sources and verified/assumed properties: [ENVIRONMENTAL_DATA_SOURCES](../scientific/ENVIRONMENTAL_DATA_SOURCES.md), [TERRAIN_METHODOLOGY](../scientific/TERRAIN_METHODOLOGY.md), [RAINFALL_METHODOLOGY](../scientific/RAINFALL_METHODOLOGY.md).

## Deliverables
Code `backend/app/services/environmental/` (raster incl. `reference_grid.py`, dem, rainfall, providers, soil, land_cover, smap, lithology, vegetation, distances, seismic, features, pipeline, manifest, external_inputs, preview, queries, catalog); models and migrations `0004` (`environmental_processing_runs`, `environmental_layers`, `environmental_features`, `earthquake_events`) and `0005` (`temporal_kind`, `aligned_file_path`, `reference_grid`); API `/api/v1/environmental/*` ([API_DOCUMENTATION](../architecture/API_DOCUMENTATION.md)); frontend `/dashboard/environmental` (tabs: overview, map layers, terrain, rainfall with Recharts, events, quality, manifest); outputs under `data/processed/environmental/<area_id>/`.

## Acceptance vs evidence
Met on synthetic data: Phase 2 reuse, Phase 3 provenance handling, DEM inspection/clip, slope/aspect, rainfall aggregation, soil and land-cover statistics, catalog reuse, USGS parsing, standardisation utilities, missing-data handling, lineage, quality reports, migration, API, frontend. Also met on synthetic data (addendum): manifest completeness and schema, grids for three UTM zones including a southern-hemisphere one, a boundary-straddling AOI, a sub-cell AOI, mixed-CRS inputs, all-nodata input, missing inputs giving NOT_AVAILABLE with a reason, skip/force semantics, the half-hourly missing-interval rule, no score-like field names; plus a live container run and a headless-browser check ([PROJECT_STATUS](../project/PROJECT_STATUS.md)). **Not met:** any real-data processing or validation; download automation for soil/land cover (by design: proposals only).

## Known limitations
- NASADEM void value, EGM96 datum and `.zip` packaging are assumptions; IMERG daily layout and units unverified; USGS time/depth units and rate limits unverified; SoilGrids CRS/nodata/URLs unverified; WorldCover nodata/tile naming unverified.
- AOI statistics at native resolution: a 10 km IMERG cell cannot describe local rainfall; an AOI smaller than a raster cell uses the touched cell and warns.
- Antimeridian bbox crossings are refused (a shapely polygon straddling 180 degrees cannot be detected this way). Reference grid: centroid-only UTM zone and hemisphere, UTM distortion across zones, large downsampling uses bilinear, no vertical datum handling, categorical raster without declared nodata gets the dtype maximum as nodata. External layers: GeoJSON-only vectors, whole-raster memory use, NDVI out-of-range count covers the whole source file.
- Unverified assumptions added by the addendum: SMAP HDF5 attributes and 36 km grid; IMERG half-hourly details; MODIS 1 km NDVI specifics. Full list: [PROJECT_STATUS](../project/PROJECT_STATUS.md) issues 22-34.
- Descriptive features only: no thresholds, classes, scores or weights.

## Dependencies
Needs Phase 2 downloads for real results; feeds Phase 5 (features), Phase 6 (series), Phase 7 (contracts). Phase 3 outputs are optional.
