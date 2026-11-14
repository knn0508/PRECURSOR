# Terrain methodology (Phase 4, DEM / slope / aspect)

Status: implemented and tested on SYNTHETIC fixtures only. `REAL_DATA_VALIDATION: NOT_PERFORMED` (no real NASADEM file exists locally). Passing synthetic tests proves the arithmetic, not agreement with real terrain.

Code: `backend/app/services/environmental/{raster,dem,features}/`, fixtures in `synthetic_raster.py`.

## 1. Slope (Horn 1981, 3x3)

Window (row 0 = north): `a b c / d e f / g h i`.

```
dz/dx (east+)  = ((c + 2f + i) - (a + 2d + g)) / (8 dx)
dz/dy (north+) = ((a + 2b + c) - (g + 2h + i)) / (8 dy)
slope = atan(sqrt((dz/dx)^2 + (dz/dy)^2))        [degrees]; percent = 100 tan(slope)
```

`dx`, `dy` are cell sizes in metres, per row.

### Geographic CRS (e.g. EPSG:4326)
Degrees are never metres. For row-centre latitude phi, CRS ellipsoid (a, e^2):
`N = a / sqrt(1 - e^2 sin^2 phi)`, `M = a (1 - e^2) / (1 - e^2 sin^2 phi)^1.5`,
`dx = N cos(phi) dlon`, `dy = M dphi` (radians). At 1 arc-second: dy ~ 30.9 m everywhere, dx ~ 30.9 m at the equator and ~15.4 m at 60 deg.
### Projected CRS
Cell size is the transform step times the CRS linear-unit factor to metres (feet and US survey feet supported). Rotated grids are rejected.
### Elevation units
Heights must be metres. A declared non-metre unit is rejected, not converted. Undeclared units are assumed metres and the assumption is reported.

## 2. Aspect

Aspect = direction the slope FACES (downslope), degrees clockwise from north, [0, 360): 0 N, 90 E, 180 S, 270 W.
`aspect = atan2(-dz/dx, -dz/dy) mod 360`. Tested: plane descending east = 90, south = 180, west = 270, north = 0.
Flat cells (slope < 1e-3 deg, `FLAT_EPS_DEG`) have no direction: aspect = NaN and the count is reported (`flat_count`). Never 0 or -1.
8-sector classes are centred on N, NE, ... (N = 337.5-22.5). Circular statistics use sin/cos: circular mean, mean resultant length R, circular std `sqrt(-2 ln R)`; if R ~ 0 the mean is undefined (None). 359 and 1 average to ~0, not 180.

## 3. NoData policy
Missing = NaN (float32 outputs, NaN nodata tag). Never converted to zero. Horn output is NaN on the 1-pixel border, on a NaN centre, and wherever any of the 8 neighbours is NaN. Statistics ignore NaN and return `None` (not 0) when nothing is valid. Mosaic gaps, AOI parts not covered by the source, and holes stay NaN and are reported.

## 4. Resampling rules (`raster/alignment.py`)
| Layer | Method |
|---|---|
| elevation, slope, soil, rainfall, InSAR | bilinear |
| LAND_COVER / categorical | nearest only; class ids never interpolated, no new ids appear |
| ASPECT | resample sin and cos bilinearly, recombine with atan2; NaN preserved; where averaged directions cancel the result is NaN (warned) |

Resampling does not add information; native and processing resolution are both reported. Downsampling by more than 2x with bilinear aliases (no area averaging) and is warned. Preferred pipeline: derive slope/aspect on the native DEM grid, then align the derived layers, rather than the reverse.

## 5. Mosaic and clip
Tiles in sorted file-name order, first valid value wins, overlap cells counted, overlap values compared (warn above tolerance), uncovered cells left NaN. Mixed CRS or resolution is an error unless an explicit target grid is supplied. Mixed or undeclared units / vertical datum tags are warned, never assumed equal. Clipping transforms the EPSG:4326 AOI to the raster CRS with pyproj (edges densified); pixel centres outside the polygon become NaN. AOI coverage % = AOI area inside the source footprint, planar in the raster CRS (for geographic rasters a ratio of square degrees, an approximation). No intersection raises `NotAvailable`.

## 6. Verified vs assumed about real NASADEM
Verified from NASA Earthdata catalog page for NASADEM_HGT v001 (web fetch, 2026-11-14): 1 arc-second spacing (~30 m), 1x1 degree tiles, HGT format, file names give the lower-left corner (e.g. `s01w047.hgt`), land between 60N and 56S, elevations in metres, reprocessing included conversion to a geoid reference, voids interpolated-filled in that product.
NOT verified (assumed, flagged in code/tags): the geoid model name (EGM96 is the commonly cited value; the catalog page did not name it); the void value -32768 (SRTM HGT convention; GDAL's HGT driver reports it, but the catalog page gave no fill value, and the page says voids were filled, so voids may be rare or absent); the horizontal datum (WGS84 assumed by the HGT driver's EPSG:4326, not stated on the page); the 3601x3601 size and `.zip` packaging with one `.hgt` (matches SRTM convention and what the code handles; the page did not describe the archive); exact member naming inside the zip.
GDAL's HGT driver reports `AREA_OR_POINT=Point` and extends the footprint half a pixel beyond the nominal 1 degree; adjacent tiles therefore share one row/column of pixel centres and appear as overlap, which the mosaic overlap rule handles. Observed only on the synthetic imitation file.
The synthetic `.hgt`/`.zip` fixtures cannot carry the synthetic tag inside the format; they are labelled by name, docstring and location only.

## 7. Limitations
- Whole-array processing (documented memory bound); fine at tile/AOI scale.
- Horn smooths and is not exact on curved surfaces (cone test tolerance 0.1 deg near the axis); slope on a noisy DEM includes DEM noise (NASADEM has errors, vegetation/building bias).
- Slope/aspect describe the DEM surface at about 30 m, not local ground conditions. They are descriptive terrain measurements: no susceptibility, risk class or score is produced anywhere in this layer.
- Planar AOI coverage and nearest-pixel-centre masking are approximations at pixel scale.
- Vertical datum differences between tiles are warned about but not corrected.
