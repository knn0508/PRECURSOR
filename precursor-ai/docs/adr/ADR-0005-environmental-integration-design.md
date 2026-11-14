# ADR-0005: Environmental integration design

- Status: ACCEPTED (the scipy rejection under "Alternatives considered" is revised for Phase 5 by [ADR-0007](ADR-0007-feature-extraction-and-labelled-dataset.md); Phase 4 code still uses no scipy)
- Date: 2026-11-14 (Phase 4)

## Context
Phase 4 must combine heterogeneous datasets (DEM, rainfall, soil, land cover, catalogs, seismic, InSAR references) without fabricating data, without silent downloads, and while staying useful when most inputs are missing (the repository has no real files).

## Decision
1. **Placement and reuse.** Code in `backend/app/services/environmental/` (same reasoning as [ADR-0004](ADR-0004-insar-placement-and-strategy.md)); inputs are Phase 2 `data_acquisitions` files, the Phase 2 landslide table, Phase 3 `deformation_products`, and files the user places in `data/external/<provider>/`. No second download or AOI system; areas are `monitored_areas`.
2. **No automatic downloads.** Providers for soil and land cover produce acquisition *proposals* and read local files. The only outbound call is the explicit `POST /areas/{id}/seismic/refresh` (anonymous, read-only USGS query).
3. **Pipeline semantics.** Ten explicit stages; a missing input is `NOT_AVAILABLE` with a reason, a stage failure is isolated, the run is `PARTIAL` rather than successful whenever anything is missing. Identical inputs and configuration (SHA-256 over file names, sizes, AOI, window) skip the stage (retry without redoing work); `force` overrides.
4. **Honest provenance.** Every layer/feature stores origin (`REAL_SATELLITE`, `SYNTHETIC_FIXTURE`, `LOCAL_UNVERIFIED`), measurement kind and `NOT_VALIDATED`. Catalog rows are never labelled real-satellite. Phase 3 products are references; synthetic and unverified ones are excluded from features.
5. **Storage.** Large rasters on disk (relative paths, never exposed); metadata, series, statistics and feature payloads in PostgreSQL (JSONB). Rainfall series live in the layer's statistics so charts need no raster read. Soil and land cover keep statistics only (clipping returns no georeference yet).
6. **Science rules.** Horn slope with metre cell sizes for geographic grids; aspect as a circular variable; categorical data only nearest-neighbour; missing data never zero; rolling/monthly sums need complete windows; no thresholds, classes, weights or scores.
7. **Dependencies.** None added to the backend (numpy, pandas via xarray, rasterio, pyproj, shapely, h5py). Frontend adds Recharts (it was documented as present but was not installed).

## Alternatives considered
Auto-downloading SoilGrids/WorldCover (rejected: approval policy, size, unverified endpoints). A separate environmental database schema per dataset (rejected: layer/feature rows cover all). Interpolating missing rainfall days (rejected: fabricates data). scipy/geopandas/rioxarray (rejected: not needed).

## Consequences
Useful with partial data and honest about gaps; soil/land cover cannot yet be drawn on the map; real-data behaviour of every reader remains to be verified, with adapter fixes expected on first real files.

## Related
[PHASE_04](../phases/PHASE_04.md), [ENVIRONMENTAL_DATA_SOURCES](../scientific/ENVIRONMENTAL_DATA_SOURCES.md)
