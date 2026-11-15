# Validation and limitations report (Phase 10, 2026-11-15)

**Intended use: research prototype, not an operational warning system.** Nothing here is a validated forecast. No ML model exists in the 10 phases, so no prediction, probability, risk class or lead time has ever been produced or validated. Every figure below was produced by a command run in the Phase 10 session; anything not run is marked `NOT_PERFORMED` or `NOT_VERIFIED`.

## 1. `REAL_DATA_VALIDATION` per phase
| Phase | Status | Basis |
|---|---|---|
| 1 Foundation | PERFORMED (software) | backend and frontend suites, live containers, health endpoint; no scientific data involved |
| 2 Acquisition | PARTIAL | anonymous CMR catalog search verified live earlier; downloads exercised with mocks and local HTTP servers (resume, checksum, retry, disk space). Per [TASK_LOG](../project/TASK_LOG.md) the ML track (M2) downloaded 35 real files (27 NASADEM, 8 WorldCover) with SHA-256 and integrity checks; that was NOT re-verified in Phase 10. No NISAR granule has ever been downloaded |
| 3 InSAR | NOT_PERFORMED | synthetic fixtures and analytic oracles only; no real GUNW processed; sign convention unverified |
| 4 Environmental | NOT_PERFORMED | synthetic data only; every real-file assumption (IMERG, SMAP, NASADEM void/datum, SoilGrids, WorldCover) unverified |
| 5 Features and dataset | NOT_PERFORMED | oracle tests on analytic surfaces; no real catalog or stack |
| 6 Time series | NOT_PERFORMED | synthetic and hand-computed series |
| 7 ML slot | not applicable (contracts) | contract tests with a test-only double |
| 8 Uncertainty | NOT_PERFORMED | hand-computed formulas; masks never run on real products |
| 9 Dashboard | PARTIAL | headless-browser runs against the live API with and without the mock flag; no real data was displayed |
| 10 Validation | this report | |

## 2. What was validated, against what, with what error
**Geospatial geometry (PERFORMED, analytic reference).** UTM zone choice, metric distance, area and CRS round-trip for seven AOIs on six continents/zones plus a polar case, against independent WGS 84 geodesic computations (`pyproj.Geod`), in `backend/tests/validation/test_phase10_validation.py`:

| AOI | EPSG | 10 km distance error | 0.1 x 0.1 degree area error | round-trip |
|---|---|---|---|---|
| Sabah | 32650 | -0.029 % | -0.058 % | 1.4e-14 deg |
| Oslo (Norway zone exception) | 32632 | -0.028 % | -0.057 % | 7e-15 deg |
| Santiago | 32719 | -0.015 % | -0.029 % | 7e-15 deg |
| Nairobi | 32737 | +0.031 % | +0.062 % | 7e-15 deg |
| Anchorage | 32606 | -0.012 % | -0.023 % | 7e-15 deg |
| Svalbard (zone exception) | 32633 | -0.040 % | -0.080 % | 2e-15 deg |
| Fiji (179.5 E) | 32760 | +0.051 % | +0.102 % | 0 |

Stated tolerances (0.1 % distance, 0.2 % area, 1e-9 degree round trip) are met; the residual is the UTM scale factor, as expected. A polar AOI selects EPSG:3031. Antimeridian-crossing AOIs are rejected (`west > east`, or coordinates beyond 180), not wrapped.
**Slope on a known plane (PERFORMED, analytic):** exact on projected grids and at two latitudes on geographic grids, `tests/environmental/test_terrain_slope_aspect.py` (earlier phases).
**InSAR phase to displacement:** hand-computed oracle and a wrapped-phase recovery test (synthetic). **InSAR vs a reference product or known-motion site: `NOT_PERFORMED`** (no real file; no RMSE or bias exists).
**Time series, uncertainty, masks:** hand-computed values (Mann-Kendall, API, Cramer-Rao bound, layover/shadow geometry). Synthetic.
**Acquisition on real files:** `NOT_PERFORMED` in Phase 10 (no download was approved).

## 3. Robustness (tests run, 2026-11-15)
Corrupt and empty rasters raise a clear `EnvError`; a corrupt HDF5 is reported as unrecognised, not a crash; missing files raise `FileNotFoundError`; oversize AOIs refused; 64 concurrent health requests from 16 threads all returned 200 (0.33 s); a bbox query over 3,000 stored events returned in 0.57 s including insertion (generous 5 s bound). Existing tests cover resumable downloads, range-ignored restart, checksum mismatch, disk-space check, stale-job recovery after restart (acquisition, InSAR, environmental) and corrupt environmental inputs. **Not performed:** multi-million-pixel memory/time profile (the 16 M-pixel grid cap is a guard, not a measurement), load testing beyond the smoke test above, real interrupted downloads of multi-GB files.

## 4. Known biases and limits
- **Inventory bias:** the NASA Global Landslide Catalog is a one-time export, last event 2017-09-28, biased to reported and accessible places and to large or fatal events; absence of an event proves nothing. It cannot validate a NISAR-era model.
- **Resolution mismatch:** IMERG ~0.1 degree (~11 km), SMAP 9-36 km, InSAR tens of metres, DEM 30 m: coarse dynamic inputs are shared by many cells.
- **Geometry:** InSAR measures line-of-sight motion along one geometry; it is not vertical or 3D motion; ascending and descending are never merged; the LOS sign convention is unverified.
- **Vegetation decorrelation:** low coherence over vegetation limits L-band and especially C-band precision; no coherence threshold is validated.
- **Atmosphere/ionosphere/orbit:** no correction exists; the Cramer-Rao bound excludes them.
- **Statistics:** time-series intervals assume independent errors; minimum-N values are working choices; overlapping InSAR pairs are serially dependent.
- **No ML:** susceptibility and trigger heads are contracts only.

## 5. Intended use and non-use
Use: scientific exploration, data engineering and method development with clearly labelled data. **Do not use** for evacuation, safety, insurance, planning or any operational decision; for any claim that an area is or is not at risk; or to present synthetic or mock output as data. The dashboard says so on every early-warning view.

## 6. Early-warning validation
Protocol only: [EARLY_WARNING_VALIDATION_PROTOCOL](EARLY_WARNING_VALIDATION_PROTOCOL.md). Results `NOT_APPLICABLE` (no model).
