---
paths:
  - "backend/app/services/**"
  - "backend/app/models/**"
  - "ai_engine/**"
  - "data/**"
---

# Geospatial rules

- Store geometry as PostGIS SRID 4326 (lon, lat order). Normalize AOIs to EPSG:4326 for search; keep the source CRS in metadata.
- Make every CRS transformation explicit (pyproj); never assume a CRS.
- Validate geometries (valid, non-empty, finite coordinates in range) before use.
- Preserve spatial metadata (CRS, extent, footprint, resolution, units, nodata) alongside files. Document raster resolution, units and extent for each dataset.
- CMR spatial matches are a superset: re-check footprints with shapely.
- InSAR/GUNW gives line-of-sight (LOS) displacement. Never present it as absolute 3D or vertical displacement without stating the assumption.
- IMERG is ~0.1 degree and ~3.5-month latency (Final Run): not real-time, not point rainfall.
- Large rasters/HDF5 stay on disk (`data/`), not in PostgreSQL.
