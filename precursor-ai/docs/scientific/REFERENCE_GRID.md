# Common reference grid and clipped soil / land-cover rasters

Status: **IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA** (synthetic rasters only). Code: `backend/app/services/environmental/raster/reference_grid.py`, `providers/base.py` (`clip_raster`, `write_clip_geotiff`), `soil/soil_processor.py`, `land_cover/land_cover_processor.py`.

## 1. Choosing the CRS from the AOI

`choose_projected_crs(aoi_wgs84)` uses the AOI **centroid** (bbox centre when only a bbox is given). Nothing is hard-coded to a region.

- UTM zone = floor((lon + 180) / 6) + 1, WGS 84: EPSG 326xx (north) / 327xx (south).
- Norway (56-64 N, 3-12 E) uses zone 32; Svalbard (72-84 N) uses zones 31/33/35/37 by longitude. Tested.
- |centroid lat| > 84: polar stereographic, EPSG:3413 (north) / EPSG:3031 (south), with a warning.
- AOI whose west and east edges fall in different zones: the centroid zone is kept and a warning names both zones and the distortion caveat.
- AOI crossing the antimeridian (west > east): **unsupported**, `EnvError`; split the AOI. Empty, invalid or non-finite AOIs raise `EnvError`.
- A user CRS (`crs=`) must be projected with metre axes; geographic, foot-based or unknown CRSs raise `EnvError`. `chosen_by` is `auto` or `user`.

## 2. Grid construction

`build_reference_grid` transforms the AOI bounding box into the CRS (edges densified), snaps the bounds outward to whole cells whose origin is a multiple of the resolution (identical inputs give an identical grid), and always yields at least 1x1 cell (a warning is added when the AOI is smaller than one cell). Default resolution 30 m. If `width*height > max_pixels` (16 M) the resolution is multiplied by an integer factor until it fits, and a warning says so; it never fails silently. Units are always metres, never degrees.

## 3. Alignment rules (`align_layer_to_reference`)

Reuses `alignment.align_to_grid`. Continuous layers: bilinear. Categorical (land cover, lithology): nearest only; the output keeps the source integer dtype and its declared nodata (an unused dtype-max is chosen when none was declared); no new ids can appear. Aspect: circular (sin/cos) resampling, so 359 and 1 degrees do not average to 180. Pixels outside the AOI polygon become NaN/nodata. Missing is never zero.

Reported with every layer: valid/missing percent, native vs processing resolution (native geographic pixels also given in approximate metres), CRS, and warnings. A source that does not overlap the grid raises `NotAvailable`; an all-nodata source is reported (0 % valid, NaN output), not an error.

**Oversampling caveat.** Resampling does not add information. When the grid is finer than the source's native resolution an explicit `OVERSAMPLING` warning is added; the values are interpolated or replicated.

## 4. Limits

- UTM distortion grows away from the zone central meridian; an AOI spanning zones carries that error (warned, not corrected).
- No vertical datum handling: elevations are used as delivered.
- Antimeridian AOIs unsupported. Zone choice uses the centroid only.
- Downsampling by large factors uses bilinear, not area averaging (aliasing warning from `alignment.py`).

## 5. Clipped soil and land-cover rasters

Previously only statistics were returned. When `out_dir` is passed, `process_land_cover` and `process_soil` also write the clipped window on the **native grid** (no resampling; the reference-grid step aligns them later) and list it in `result.rasters` (JSON-serialisable dicts).

- Land cover: `land_cover.tif`, integer dtype and declared nodata preserved, polygon-masked cells set to nodata. Tiles are merged by copy only when CRS, resolution, dtype, nodata and pixel grid agree; otherwise one file per tile with a warning. Tags: legend JSON (official WorldCover names/colours), version, year, source names, and the synthetic tag when the source has it.
- Soil: one float32 raster per property/depth/statistic named `soil_<prop>_<top>-<bottom>cm_<stat>.tif`, values = raw / documented ISRIC factor, NaN nodata; tags hold units, scale factor and raw units.
- `ClipResult.transform` is the window affine; `write_clip_geotiff` writes it.
