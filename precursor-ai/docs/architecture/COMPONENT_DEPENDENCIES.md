# Component dependencies

```
api/v1 -> services -> repositories -> models -> PostgreSQL/PostGIS
api/v1/data/deps -> orchestrator, search_service, auth (injected)
orchestrator -> providers, download_manager, validation_service, metadata_service
providers -> cmr.py (earthaccess; the only mocked NASA seam) ; asf provider -> asf_search
download_manager -> authentication (Earthdata session) , storage
api/v1/insar -> services/insar/runs -> adapters, processing, outputs, storage (reads data_acquisitions; never imports data_acquisition providers/auth)
services/insar -> h5py, rasterio, numpy, pyproj, shapely only (no network)
api/v1/environmental -> services/environmental/pipeline/runs -> raster (incl. reference_grid), dem, rainfall, smap, providers (local files only), soil, land_cover, lithology, vegetation, distances, external_inputs, features, manifest, preview, queries
services/environmental reads data_acquisitions, landslide_events, deformation_products (never imports data_acquisition providers/auth); only providers/usgs_earthquake.py uses HTTP
api/v1/features_cv -> services/features_cv/{pipeline,dataset_run,registry} (read-only; reads manifests from data/processed)
services/features_cv -> reads the Phase 4 manifest.json + aligned rasters (environmental/raster, dem/slope reused); events.py reads landslide_events; numpy, scipy, scikit-image, pandas, pyarrow, rasterio; no network, no ML
cli -> same services as the API (no HTTP)
frontend -> api-client -> /api/v1
ai_engine -> (future) never imports FastAPI
```

Rules: dependencies point inward; route handlers make no NASA calls; `core/geo_env` imports before geo libraries.

| Runtime dependency | Used for |
|---|---|
| earthaccess, asf_search, requests | NASA catalog + downloads |
| numpy (explicit since Phase 3) | array processing |
| h5py, rasterio, xarray, netCDF4, shapely, pyproj | file validation, footprints, CRS |
| scikit-image, scipy, pyarrow (pinned, Phase 5) | GLCM texture; ndimage filters and cKDTree; Parquet export ([ADR-0007](../adr/ADR-0007-feature-extraction-and-labelled-dataset.md)) |
| SQLAlchemy 2, GeoAlchemy2, Alembic, psycopg | persistence |
| Next.js 16, React 19, MapLibre, Three/R3F, GSAP, Lenis | frontend |

Versions: `backend/requirements.txt`, `frontend/package.json`.
