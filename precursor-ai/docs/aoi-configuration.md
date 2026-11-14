# AOI configuration

An Area of Interest (AOI) is the polygon that scopes every catalog search. **No default AOI ships with the project and none is invented.** Put your own file in `data/aoi/` (or `AOI_DIR`), or pass geometry inline to the API.

## Accepted input

| Form | Notes |
|---|---|
| GeoJSON | `Geometry`, `Feature` or `FeatureCollection` (features are unioned). Files: any extension except `.wkt`/`.txt`. |
| WKT | File extension `.wkt` or `.txt`. |
| API | `AOIInput`: exactly one of `monitored_area_id` (a Phase 1 area) or `geometry` (GeoJSON), plus optional `name`. |

## Rules (`app/services/data_acquisition/aoi.py`)

- Geometry type must be `Polygon` or `MultiPolygon` (points/lines are rejected).
- CRS is EPSG:4326, coordinates in (longitude, latitude). Another CRS can be given programmatically and is reprojected to EPSG:4326.
- Must be non-empty, topologically valid (no self-intersection), and within lon -180..180 / lat -90..90 (a swapped axis order usually fails this).
- Size cap: bounding box width and height must each be at most `MAX_AOI_BBOX_DEGREES` (default `5`) degrees. This prevents accidental country-scale downloads.

Invalid AOIs raise `AOIError` (exit code 2 in the CLI; validation error in the API).

## How the AOI is used in a search

1. CMR gets the exact **polygon** when it is a single Polygon with no holes and at most 100 vertices (ring is re-oriented counter-clockwise); otherwise the **bounding box**.
2. Because a bbox (and CMR's own matching) is a superset, every returned footprint is re-checked with an exact shapely intersection against the AOI. Non-intersecting hits are dropped.
3. NASADEM additionally restricts to the integer-degree tiles that overlap the AOI.

## Example

```geojson
{
  "type": "Feature",
  "properties": {"name": "example"},
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[100.0, 10.0], [100.5, 10.0], [100.5, 10.5], [100.0, 10.5], [100.0, 10.0]]]
  }
}
```

**ILLUSTRATIVE SHAPE ONLY: not a verified coverage area.** The coordinates are arbitrary and say nothing about NISAR coverage, terrain or landslide risk. Replace them with your own area.
