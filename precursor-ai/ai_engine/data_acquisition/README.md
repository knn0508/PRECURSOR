# data_acquisition

**Future responsibility:** search, download and catalogue SAR products (Sentinel-1 via ASF/Copernicus, NISAR when available) and external layers (DEM, rainfall, land cover) for a monitored area.

- Writes raw files to `data/raw/` and external layers to `data/external/`.
- Records provenance in `satellite_acquisitions` (source, date, orbit, polarization, product type, checksum).
- Must record the product's exact source URL/ID so results are reproducible.
