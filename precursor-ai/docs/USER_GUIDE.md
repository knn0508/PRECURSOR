# User guide

PRECURSOR AI is a **research prototype for exploring SAR and environmental data for landslide early-prediction research. It is not an operational warning system.** Do not use it for evacuation, safety or planning decisions. No prediction model exists: prediction screens show N/A, or, only in a build with the mock flag, a layout test labelled `MOCK DATA: NOT A PREDICTION`.

## Start and open
`docker compose up -d --build`, then open http://localhost:3000. The API documentation is at http://localhost:8000/docs.

## Workflow
1. **Pick or add an area** (Workspace, or Monitored Areas). Add one by uploading a GeoJSON Polygon/MultiPolygon in lon/lat (any region; searches and downloads are limited to areas of at most 5 x 5 degrees). Drawing on the map is not available.
2. **Find satellite data** (Data Acquisition -> Search). A search result is a catalog entry (`metadata_only`), not a file. Maturity (VALIDATED / PROVISIONAL / BETA) is shown on every granule; only VALIDATED is searched by default.
3. **Download** only what you intend to use (Downloads). This needs Earthdata credentials in `.env`; the app refuses with a clear message if they are missing. A downloaded file is checked for integrity, which is not scientific validation.
4. **Process**: Environmental page -> Overview -> process the area (terrain, rainfall, soil, land cover, events, reference grid, manifest). InSAR page -> choose a stored product and process it. Jobs show progress; missing data is shown as missing, never as zero.
5. **Look at the results** in Workspace: Map & layers (opacity, legend, units, CRS, resolution, period, source badge), Terrain, Rainfall & series (descriptive trend statistics), Landslides & earthquakes, Metadata & lineage.
6. **Early warning tab**: N/A until a real, validated model exists.

## Reading the labels
Source badges: REAL SATELLITE (as delivered, not validated), REAL DERIVED (computed here or unverified local file), SYNTHETIC DEMO (test data, not a measurement), STATISTICAL (descriptive statistic), MODEL PREDICTION (none exists), PLACEHOLDER. Red/amber banners mean synthetic or unverified. A deformation raster measures motion along the radar line of sight; it is not vertical motion and not a risk map.

## Limits you should know
The landslide catalog ends in 2017 and is biased to reported places; IMERG rainfall is ~11 km and not real time; SMAP is 9-36 km; InSAR sign convention is unverified; nothing has been validated on real data yet. Full list: [VALIDATION_REPORT](scientific/VALIDATION_REPORT.md) and [SCIENTIFIC_LIMITATIONS](scientific/SCIENTIFIC_LIMITATIONS.md).
