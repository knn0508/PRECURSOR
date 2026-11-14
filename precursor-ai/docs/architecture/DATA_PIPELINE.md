# Data pipeline

## Implemented (Phase 2)
Implementation detail, states and CLI/API usage: [../phase-2-data-acquisition.md](../phase-2-data-acquisition.md) (canonical). Storage: [../data-storage.md](../data-storage.md). Validation: [../data-quality-validation.md](../data-quality-validation.md).

```
CMR/ASF catalog -> provider -> GranuleRecord (metadata_only) -> register (DISCOVERED)
  -> orchestrator queue -> DownloadManager (.part, resume, retry, atomic rename; Earthdata auth)
  -> FileValidationService (integrity) -> VALIDATED + manifest in data/metadata/
Landslide catalog CSV -> import -> landslide_events (no auth)
```

Status: search verified live (anonymous); download/validation verified with mocks and synthetic files only.

## Implemented (Phase 3): processing of already-downloaded files
```
data_acquisitions row (file in data/raw) or data/samples/insar -> inspect (adapter per product)
  GUNW: validate -> LOS displacement (mm) + coherence + mean velocity -> COG in data/processed/insar -> deformation_products
  GSLC/GCOV: inspection-only   Sentinel-1: BLOCKED_MISSING_INPUT (no SNAP/ISCE/SNAPHU)
  every run -> quality_report.json + inspection.json + metadata json; status/stages in insar_processing_runs
```
Detail: [../scientific/INSAR_METHODOLOGY.md](../scientific/INSAR_METHODOLOGY.md). Verified on SYNTHETIC files only.

## Implemented (Phase 4): environmental integration
```
Phase 2 NASADEM/GPM files + data/external soil/land cover + DB (landslides, earthquakes, Phase 3 products)
  + user-provided lithology, NDVI, river/fault/road GeoJSON in data/external/<subdir>/ ; Phase 2 SMAP L3 files
  -> DEM -> TERRAIN -> RAINFALL -> SMAP -> SOIL -> LAND_COVER -> LITHOLOGY -> NDVI -> DISTANCES -> HISTORICAL_LANDSLIDES -> SEISMIC -> INSAR
  -> REFERENCE_GRID -> FEATURES -> MANIFEST -> QUALITY      (16 stages)
  -> environmental_layers / environmental_features / run quality report; rasters in data/processed/environmental/<area_id>/ (natives, aligned/ copies, features/manifest.json)
```
REFERENCE_GRID picks a projected metre grid (UTM from the AOI centroid, or the user's `grid_crs`; default 30 m) and aligns every raster layer to it, keeping native files; layers produced directly on the grid (lithology, NDVI, distances) are their own aligned copy. MANIFEST then lists every layer kind. Method: [../scientific/REFERENCE_GRID.md](../scientific/REFERENCE_GRID.md); user layers: [../scientific/EXTERNAL_LAYERS.md](../scientific/EXTERNAL_LAYERS.md); SMAP: [../scientific/SMAP_METHODOLOGY.md](../scientific/SMAP_METHODOLOGY.md); decision: [ADR-0006](../adr/ADR-0006-stack-manifest-and-reference-grid.md). Rainfall is daily by default; `rainfall_resolution=half_hourly` is optional.
Missing inputs end a stage NOT_AVAILABLE (never zero); identical inputs are skipped on re-run. Detail: [../phases/PHASE_04.md](../phases/PHASE_04.md). Verified on SYNTHETIC data only.

## Planned (not implemented; no code exists)

| Stage | Phase | Input -> output |
|---|---|---|
| Feature extraction | 5 | processed rasters -> feature tables |
| Time series | 6 | displacement stack -> statistical metrics |
| Risk / uncertainty / XAI | 7-8 | contracts only until ML is separately authorized |

Original files in `data/raw` are never modified; derived products go to `data/processed`.
