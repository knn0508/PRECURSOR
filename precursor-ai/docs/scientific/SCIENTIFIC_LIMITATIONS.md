# Scientific limitations

Canonical list of limits that must be stated wherever the related data is used. Dataset catalogue and collection IDs: [../nasa-data-sources.md](../nasa-data-sources.md) (canonical; no separate DATA_SOURCES file is kept to avoid duplication).

| Topic | Limitation |
|---|---|
| Product maturity | NISAR products are VALIDATED / PROVISIONAL / BETA. Do not assume every maturity exists per product; do not mix silently. Default is VALIDATED only. No validated SME2 soil-moisture existed at last check. |
| Catalog hit vs data | A metadata hit is not a downloaded file; a downloaded file is not scientifically validated. `VALIDATED` status means file integrity checks passed. |
| Coverage | Never assert NISAR coverage of an AOI until the catalog returns granules. Absence of granules is reported, not filled. |
| IMERG | Final Run ~3.5-month latency; ~0.1 degree (~10 km) grid; not real-time; coarse for slope-scale rainfall. |
| Global Landslide Catalog | One-time export, last event dated 2017-09-28 (corrected 2026-11-15, [M1 census](../../ml/reports/M1_census_and_download_list.md)); incomplete, biased towards reported events; no event does not mean no landslide. Day/month order unverified on real CSV. |
| NASADEM | 1 arc-second (~30 m) elevation; terrain derivatives belong to later phases. |
| SMAP | SPL3SMP_E (9 km, top ~5 cm, m3/m3): coarse for slope-scale use; AM and PM kept separate; missing days stay missing; quality filter optional. HDF5 attribute names for units/fill in real files UNKNOWN. [SMAP_METHODOLOGY](SMAP_METHODOLOGY.md). |
| Reference grid / alignment | One projected metre grid per run (UTM from the AOI centroid); resampling adds no information; UTM distortion across zone boundaries; no vertical datum handling; antimeridian bbox refused. [REFERENCE_GRID](REFERENCE_GRID.md). |
| User-provided layers (lithology, NDVI, distances) | Only what the user places in `data/external/`; lithology names only from the user's legend; NDVI scaling only when declared; distances are straight-line metres, GeoJSON-only vectors, accuracy equals the user's data. Never a susceptibility class. [EXTERNAL_LAYERS](EXTERNAL_LAYERS.md). |
| InSAR (Phase 3) | GUNW displacement is LOS, relative to an unspecified reference, subject to unwrapping and atmospheric/ionospheric error; no corrections are applied; not 3D. The phase sign convention and the "differential, unwrapped" assumption are **unverified** (`SIGN_CONVENTION_VERIFIED=false`). Velocity is a single-interferogram mean, not a time series. |
| Environmental layers (Phase 4) | Descriptive measurements and summaries of source data, not risk. Everything is verified on synthetic data only; no real file processed. AOI statistics at native resolution cannot describe finer scales (IMERG ~10 km). Soil and land cover provide statistics and clipped native-grid maps. |
| Rainfall | Satellite estimate, not gauge truth; monthly/rolling sums only when the whole period is observed; missing days stay missing. IMERG daily file layout/units unverified from official sources. The optional half-hourly product counts a day only when all 48 intervals are present; its file details are partly UNKNOWN. |
| Soil / land cover | SoilGrids values are modelled predictions with documented scaling; WorldCover classes are not risk labels. Download-and-place workflow only. |
| Earthquakes | Independent USGS observations; no causal link to landslides; time/depth units and rate limits unverified. |
| Deformation vs landslide / risk | Deformation is evidence of ground motion, not proof of failure or imminence. A deformation raster is a measurement, not a landslide risk map or prediction. |
| Risk / ML | No model exists. No risk score is a probability. See [ADR-0002](../adr/ADR-0002-ml-deferral.md). |
| Live verification | As of 2026-11-14 no real NASA file has been downloaded, validated or InSAR-processed. Phase 2 validators and all Phase 3 processing are tested on SYNTHETIC files only: `REAL_DATA_VALIDATION: NOT_PERFORMED`. |
| HDF5 layout | NISAR dataset paths are discovered by name and are unverified against a real granule. |
| Sentinel-1 / GSLC / GCOV | No Sentinel-1 processing (tools not installed). GSLC and GCOV give no displacement. |
| Time series (Phase 6) | Descriptive statistics of observed values; intervals assume independent errors; minimum-N values are working choices; Phase 3 gives interferogram pairs, not a displacement time series; no forecast. See [TIME_SERIES_METHODOLOGY](TIME_SERIES_METHODOLOGY.md). |
| Uncertainty (Phase 8) | Ledger of recorded data-quality facts only; predictive uncertainty is NOT_ESTIMATED; the Cramer-Rao bound is a lower bound for phase noise, not total error; masks need caller-supplied geometry and thresholds. See [UNCERTAINTY_AND_RELIABILITY](UNCERTAINTY_AND_RELIABILITY.md). |
| Prediction (Phases 7, 9) | The ML slot returns MODEL_NOT_TRAINED; mock views are labelled layouts, never data. See [PREDICTION_DESIGN](PREDICTION_DESIGN.md). |
| Validation (Phase 10) | Geometry validated against geodesic references; no real-data, InSAR-accuracy or early-warning validation exists. Research prototype, not an operational warning system. See [VALIDATION_REPORT](VALIDATION_REPORT.md). |
