# ADR-0006: Stack manifest and common reference grid

- Status: ACCEPTED
- Date: 2026-11-14 (Phase 4 completion addendum)

## Context
Phase 4 produced per-dataset layers with provenance, but a later phase (Phase 5 onward) needs one consistent, inspectable data stack: every raster on the same grid, static and dynamic data distinguished, series and vector data listed, and the whole thing described in one place. The repository has no real data, so the design must be honest about gaps.

## Decision
1. **Manifest = inventory built from the database.** `GET /api/v1/environmental/areas/{id}/manifest` and `data/processed/environmental/<area_id>/features/manifest.json` (written by the `MANIFEST` stage) list every `LayerKind`. A dataset that was never processed appears as `NOT_RUN` with a reason; a processed one carries units, CRS, native and processing resolution, source, date range, origin and a synthetic flag, `validation_status`, nodata, coverage, provenance and a `lineage_hash`. File names only, never paths. Rasters are `kind=raster`; rainfall and SMAP are `series`; seismic and cataloged landslides are `vector`.
2. **`temporal_kind` (static|dynamic)** is a column on `environmental_layers` (migration `0005`, default `static`) set from a single table (`TEMPORAL_OF`): terrain, soil, land cover, lithology, distances and the catalog are static; rainfall, SMAP, NDVI, seismic and InSAR are dynamic.
3. **Lineage hash** = SHA-256 over provenance, input hash, output checksum, type and version: it changes when any source, option or output changes.
4. **Reference grid.** The REFERENCE_GRID step chooses a projected metre CRS from the AOI centroid (UTM zone; polar stereographic beyond 84 degrees; never hard-coded; an AOI straddling a zone boundary keeps the centroid zone with a warning; antimeridian crossing is refused) or accepts a user CRS that is projected and metre-based. Default cell 30 m, user-overridable; the grid is snapped to multiples of the resolution so it is reproducible, covers at least one cell, and is coarsened with a warning above a pixel cap. The grid is stored on the run (`reference_grid` JSONB) and in the manifest.
5. **Alignment keeps natives.** Every raster layer keeps its native-grid output in `file_path`; an aligned copy goes to `aligned/` and is recorded in `aligned_file_path`. Alignment reuses `align_to_grid`: bilinear for continuous, nearest for categorical, circular-aware for aspect; pixels outside the AOI polygon become nodata. Oversampling beyond native resolution is warned, not hidden.
6. **User-provided layers, no downloads.** Lithology, NDVI and the river/fault/road vectors are read from `data/external/<subdir>/`; vectors are GeoJSON only (no fiona/pyogrio/geopandas); lithology classes and names come only from the user's sidecar legend (never invented); absent input = `NOT_AVAILABLE`.
7. **Distances** are computed in the metric grid CRS from pixel centres with shapely's vectorised nearest search, in row blocks, never in degrees; no scipy.
8. **Optional inputs:** IMERG half-hourly (a day is observed only when all 48 intervals are present) and SMAP series; daily IMERG stays the default. Soil and land cover now also write clipped map rasters.

## Alternatives considered
Storing aligned rasters only (rejected: loses the native product). A fixed grid CRS or resolution (rejected: region-specific). Interpolating partial half-hourly days (rejected: fabricates data). scipy distance transform or geopandas (rejected: new dependencies, not required).

## Consequences
A single reproducible stack description that downstream phases can consume; every limit is visible. UTM distortion applies across zone boundaries; vector formats beyond GeoJSON need an approved dependency; all behaviour is verified on synthetic fixtures only.

## Related
[ADR-0005](ADR-0005-environmental-integration-design.md), [PHASE_04](../phases/PHASE_04.md), [REFERENCE_GRID](../scientific/REFERENCE_GRID.md)
