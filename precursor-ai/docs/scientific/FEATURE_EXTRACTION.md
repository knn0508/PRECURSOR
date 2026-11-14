# Feature extraction methodology (Phase 5)

Code: `backend/app/services/features_cv/` ([ADR-0007](../adr/ADR-0007-feature-extraction-and-labelled-dataset.md)). All features are DESCRIPTIVE numbers computed from the Phase 4 aligned stack. Nothing here is a risk score, probability, class or prediction. Verified on SYNTHETIC data only (`REAL_DATA_VALIDATION: NOT_PERFORMED`).

## Rules that apply to every feature
- Missing is NaN, never zero. A NaN centre, a window with too few valid cells, and the raster border (where the full neighbourhood does not exist) all give NaN.
- Cell sizes are metres (Phase 4 `cell_sizes_m`), never degrees. The Phase 4 reference grid is projected and metre-based.
- No silent resampling: inputs on different grids are refused. Texture features live on a coarser BLOCK grid with its own transform, declared in the manifest.
- Window sizes are parameters, recorded in pixels (`window_px`) and metres (`scale_m`). Names carry the parameter (`local_relief_w5`), so changing a parameter changes the feature name, not its meaning.
- The feature schema is versioned (`FEATURE_SCHEMA_VERSION`): a new feature is a MINOR change; a changed definition, unit or name is MAJOR.

## Terrain features (`terrain.py`; source layers ELEVATION, SLOPE)
| Feature | Definition | Unit | Oracle test |
|---|---|---|---|
| `local_relief_w{N}` | max - min elevation in an N x N window (needs >= `min_valid_fraction`, default 0.5, valid cells) | m | plane: gradient x span |
| `terrain_ruggedness_index` | Riley et al. (1999): sqrt(sum over 8 neighbours of (z_n - z_centre)^2) | m | plane: sqrt(6) x gradient x cell |
| `curvature_laplacian_s{sigma}` | Laplacian of the Gaussian-smoothed surface (NaN-aware normalised convolution; data never extended into missing cells). **Positive = concave-up (bowl/valley), negative = convex-up (ridge).** | 1/m | paraboloid k(x^2+y^2): 4k |
| `slope_break` | magnitude of the spatial gradient of slope (central differences) | degree/m | linear slope ramp |
| `lineament_density_w{N}` | fraction (0-1) of Canny edge pixels from hillshades at several azimuths, inside an N x N window; edges within one cell of missing data are dropped | fraction | scarp responds, plane gives 0 |

Choices and limits:
- Profile and plan curvature are NOT provided: their sign conventions differ between sources and an unverified convention would be a silent error.
- Canny thresholds (`canny_low`, `canny_high`) are edge-detector parameters on a 0-1 hillshade, not hazard thresholds. Defaults (0.02 / 0.06, sigma 1, azimuths 0/45/90/135/225/315, sun altitude 45 degrees) are working values chosen on synthetic terrain; they are NOT tuned or validated for any real landscape.
- Hillshade-based lineaments depend on the sun azimuths used; a lineament parallel to every azimuth would be missed.
- Local relief, TRI, curvature and slope break are computed tile by tile (`tiled_apply`, halo = filter reach) and equal the whole-array result (tested). Lineament density is computed on the whole raster because Canny hysteresis is not tile-invariant. The grid is capped by Phase 4 at 16 M pixels.
- If the SLOPE layer is absent the slope-break input is re-derived from the aligned ELEVATION (Horn) and the manifest says so.

## Texture features (`texture.py`)
GLCM statistics (contrast, dissimilarity, homogeneity, energy, correlation, ASM) per non-overlapping `texture_window_px` block (default 16), averaged over 4 directions at distance 1 (symmetric, normalised). Default layers: SLOPE and NDVI.
- The raster is quantised to `texture_levels` (default 16) between bounds that are recorded. SLOPE uses fixed bounds 0-90 degrees and NDVI -1..1 (AOI independent, so comparable across AOIs); other layers would use their own min/max. Out-of-range values are clipped and counted.
- A block with any missing pixel is NaN; partial edge blocks are dropped; a raster smaller than one window is NOT_AVAILABLE.
- `correlation` of a constant window is NaN (scikit-image would return 1.0, which is a convention, not a measurement).
- Oracle: a two-level checkerboard gives contrast = (levels-1)^2 / 2 (verified).
- Block-grid features are not sampled per point in dataset schema 1.0.0.

## Change features (`change.py`) and the refusal guard
`ndvi_difference` (later - earlier), `coherence_change` (later - earlier), `insar_velocity_gradient` (spatial gradient magnitude of one dated real velocity raster). They are produced ONLY from dated inputs of REAL_SATELLITE origin on one grid with equal units and layer type, with distinct dates. Synthetic, unverified, undated, same-date, mixed-unit or mixed-grid inputs raise `ChangeDetectionRefused` listing every reason; the pipeline records the feature as NOT_AVAILABLE. The Phase 4 stack holds one layer per type, so in practice all three are NOT_AVAILABLE until two dated real inputs are supplied. The velocity gradient is a spatial measure (one real dated product); a change in velocity between epochs is an acceleration measure and belongs to Phase 6 (a flagged choice, not user-specified).

## Normalisation
Optional (`--normalise zscore|minmax`): parameters (mean/std or min/max, valid count) are fitted on valid pixels and RECORDED in the manifest; the stored rasters stay raw. The exporter applies the recorded parameters. A constant or empty raster cannot be normalised and is reported, not forced.

## Outputs and provenance
`data/processed/features/<area_id>/rasters/<feature>.tif` (COG, float32, NaN nodata, CRS and transform preserved) and `manifest.json` with schema/code version, SHA-256 of the Phase 4 manifest, parameters, `seed: null` (no randomness), per-feature statistics and array hash, synthetic flag and the NOT_AVAILABLE list with reasons. Re-running on the same inputs gives identical array hashes (tested).

## ModelInputSpec (feature contract for a future model)
`schema.py` defines `ModelInputSpec` (feature names, feature/dataset schema versions, nodata policy, grid CRS and resolution, normalisation parameters, source manifest hash) and `validate_against(manifest)`: MAJOR version equal, every named feature present with status DONE, CRS and resolution equal. The Phase 7 model registry is expected to call it at model-load time. Phase 5 loads no model and implements no `services/prediction/`.

## What is not verified
Everything above runs on synthetic fixtures. Window sizes, Canny parameters, texture window/levels and the `min_valid_fraction` default have no real-data justification yet. No feature has been checked against an independent reference product.
