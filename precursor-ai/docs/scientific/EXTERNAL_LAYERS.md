# External (user-provided) layers: lithology, NDVI, distance to river/fault/road

Status: **IMPLEMENTED_BUT_NOT_TESTED_WITH_REAL_DATA.** Tests use labelled synthetic fixtures only (`external_synthetic.py`); passing them is not real-data validation. Nothing is downloaded: the user places files in `data/external/<subdir>/` (`lithology`, `ndvi`, `rivers`, `faults`, `roads`). Output layers are descriptive; no scores, thresholds, weights, classes of susceptibility or ML.

## Accepted formats

| Layer | Input | Notes |
|---|---|---|
| Lithology | categorical GeoTIFF (class ids) or GeoJSON polygons | plus optional sidecar `<stem>.legend.json` |
| NDVI | GeoTIFF (generic NDVI or MODIS MOD13/MYD13 NDVI layer) | |
| Distances | GeoJSON (`.geojson`/`.json`) points, lines or polygons | EPSG:4326 unless a legacy `crs` member declares otherwise |

**Vectors are GeoJSON only.** Shapefile and GeoPackage are unsupported until a dependency (geopandas/fiona/pyogrio) is approved; such files are rejected with a clear message. Rasters need a CRS (never guessed). Discovery (`discover_external`) lists files whose extent intersects the AOI, ignores `*.legend.json`, never leaves `data/external`, and returns `[]` for a missing directory.

## Lithology legend sidecar

```json
{"classes": [{"id": 10, "name": "unit name", "color": "#aabbcc"}], "attribute": "property name (vectors)", "source": "citation"}
```

Names come only from the user. No legend: class ids are kept, named `class N`, with a warning that names are unknown. Ids in the data but not in a given legend are reported as unknown classes (never dropped, never named). Vectors: attribute values are matched to legend names (or ids); values not in the legend get stable ids from the sorted unique values (after the highest legend id), recorded in the result `legend`. Overlapping polygons: the later feature wins. Rasters are resampled with NEAREST only (no new ids). Output: uint16, nodata 65535, class distribution in % of valid AOI pixels. No hardness/erodibility meaning is attached.

## NDVI scaling rules

Scaling is applied only if the file's own tags/scale metadata (`scale_factor`, `add_offset`, GDAL scale) or the explicit `scale_factor=` option say so. `_FillValue`/nodata and a `valid_range` tag are honoured (in raw units). After any scaling, values must lie in [-1, 1]; others are invalid (NaN), counted and reported, never clipped. Masking happens before bilinear resampling. Observation date comes from tags or file name (`A<YYYY><DDD>`, `YYYY-MM-DD`), else `UNKNOWN`.

Verified (official, https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod13q1-061, read 2026-11-14): MOD13Q1 v061 "250m 16 days NDVI": int16, fill -3000, valid range -2000..10000, scale factor 0.0001; generated every 16 days at 250 m.
Assumed / not verified here: 1 km MOD13A2 specifics; that a user's file keeps these tags (hence tags are required for auto-scaling; MOD13-like names without tags only warn). The 16-day value is a composite, not a single-day observation.

## Distance method and limits

Geometry is transformed from its declared CRS into the (projected, metre) grid CRS with pyproj first; a geographic or non-metre grid is refused. Output = Euclidean distance in metres from each pixel centre to the nearest feature (`shapely.STRtree.query_nearest`), computed in blocks of 200,000 pixel centres; grids over `max_cells` (default 4,000,000) are refused. All input features are used, including those outside the AOI. Polygons: distance to the filled area (0 inside). Invalid/empty/unsupported geometries are skipped, counted and warned (status PARTIALLY_PROCESSED). Limits: straight-line only (not along roads, rivers, or terrain); no network/path distance; vertices are transformed and edges are straight in the target CRS (negligible for normal AOIs); accuracy equals the user's vector accuracy; `discover_external` only selects files whose bbox meets the AOI (optional `vector_buffer_deg`), so a file lying entirely outside it is not found by default.

## Resolution statements

Output is on the pipeline's target grid (processing resolution, metres). Native resolution of rasters is reported; resampling adds no information (upsampling cannot recover detail finer than native). Vector layers have no native raster resolution. An AOI smaller than a pixel/source cell uses the touched cell and says so. Statistics cover AOI pixels (pixel centre inside the AOI); the written raster is not masked to the AOI polygon.

## NOT_AVAILABLE rules

`NotAvailable` is raised when no input covers the AOI, when a vector holds no usable feature, or when the input gives no valid pixel in the AOI (all nodata / all invalid; reported as valid 0%, nothing is written). Missing is NaN or the declared nodata, never 0. `EnvError`: geographic/non-metre grid, invalid legend, non-integer class ids, CRS missing, unsupported formats, grid above `max_cells`.
