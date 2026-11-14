# Labelled sample dataset (Phase 5)

Code: `backend/app/services/features_cv/{dataset,dataset_run,events,export}.py` ([ADR-0007](../adr/ADR-0007-feature-extraction-and-labelled-dataset.md)). This is a DATA PRODUCT for a future model. No model is trained, run or scored here. Verified on SYNTHETIC events and rasters only (`REAL_DATA_VALIDATION: NOT_PERFORMED`).

## Inventory bias (read first)
The NASA Global Landslide Catalog is a one-time export (current to 2016-03-07), media/report-derived, incomplete and biased toward reported, accessible, populated places. Absence of an event proves nothing. Consequences carried into every dataset manifest as `caveats`:
- EVENT samples over-represent places where landslides get reported.
- BACKGROUND samples are unlabelled places, NOT proven stable ground. They are never called "negatives".
- The class balance is set by the chosen background ratio, not by nature; the true event rate is unknown.

## Samples
Table `samples.parquet` (one row per sample), `excluded.json`, `manifest.json` under `data/processed/datasets/<area_id>/`. No database table, no migration.

Identity: `sample_id`, `sample_type` (`EVENT` | `BACKGROUND`), `is_event` (1/0), `source_event_id`, `row`, `col`, `x_m`, `y_m` (grid CRS), `lon`, `lat`, `event_date`, `accuracy_radius_m`, `buffer_m`, `terrain_stratum`, `block_id`, `split_spatial`, `split_temporal`.
Static features: `static__<LAYER or feature>` for every Phase 4 raster layer on the reference grid (elevation, slope, soil, land cover, lithology, distances, NDVI as a single-date snapshot) and every Phase 5 reference-grid feature, sampled at the nearest cell (no interpolation; NaN stays NaN). Dynamic InSAR layers and block-grid texture features are not sampled (listed in `not_sampled_layers`).
Reserved dynamic columns `dyn__{rainfall|smap_soil_moisture|insar_velocity}__t_minus_{1,3,7,14,30}d`: all NaN, listed in the manifest as `NOT_AVAILABLE` with the reason "per-point dynamic features deferred to Phase 6". No AOI-mean proxy values. For EVENT rows `anchor_t_minus_{k}d` holds the date `event_date - k days` so Phase 6 can fill them; BACKGROUND rows have no anchor date (the background reference-date policy is a Phase 6 decision).
No column or key is a score, probability, class or prediction (a test scans all names).

## Event handling
`location_accuracy` is read from `original_attributes` (no model column). Documented lookup (NOT_VERIFIED against a real catalog file):

| Value | Radius |
|---|---|
| `unknown`, empty, `n/a` | UNKNOWN: event EXCLUDED (`accuracy_unknown`) |
| `exact` | 0 m (stated exact; its true positional error is NOT_VERIFIED); the minimum buffer still applies |
| `<number> km` / `<number> m` | number x 1000 / x 1 metres |
| anything else (negative, "about 3 km", exponents) | EXCLUDED (`accuracy_unparseable`) |

Other exclusions, each listed with a reason and never repaired: `no_coordinates`, `no_date` (missing or unparseable), `accuracy_exceeds_max` (optional cap `max_accuracy_radius_m`, default none), `outside_grid`, `on_nodata`. Events with usable coordinates still repel background samples even when excluded.

## Background sampling (one strategy implemented)
Stratified by terrain: quantile bins (`n_strata`, default 5) of the SLOPE layer (or slope derived from ELEVATION; the source is recorded), quota per bin proportional to its valid-pixel area (largest remainder), seeded shuffle (`numpy.random.default_rng(seed)`), no sampling in nodata, buffer rule `max(2 x accuracy radius, min_buffer_m)` around EVERY located catalog event in the metric grid CRS (`min_buffer_m` default = 2 cells; events with unknown accuracy use `unknown_buffer_m`, default = the largest known buffer). The ratio (`background_ratio`, default 1.0 per event), the seed, the bin edges and the per-bin requested/accepted/shortfall are recorded. A shortfall (not enough room outside the buffers) is reported as a warning and never filled. Documented alternative, NOT implemented: uniform random background over valid pixels.
Limit: the buffer widths are a documented choice (twice the stated location uncertainty), not a validated physical separation distance. The loader fetches catalog events within a 0.25 degree margin of the AOI so buffers work near the edge.

## Splits and the leakage guarantee
- **Spatial-block:** block id = grid-origin-relative floor(x / `block_m`), floor(y / `block_m`) (default block: a fifth of the shorter grid side, at least 10 cells). Whole blocks go to train or test (seeded, `test_fraction` default 0.2). Train samples closer than `gap_m` (default: the largest event buffer) to any test sample are relabelled `gap` and belong to neither split. With fewer than 2 populated blocks everything is `train` and a warning says so.
- **Temporal:** cut-off date (`temporal_cutoff`, or the event-date quantile for the test fraction). EVENT rows: train if `event_date <= cutoff`, test otherwise. BACKGROUND rows are undated: they are assigned by a seeded random draw in the events' test proportion, which carries NO temporal meaning (stated in the manifest). Spatial proximity across the cut-off is allowed (same region, different time).
- `check_leakage` runs inside the builder and the build fails if it finds: a train/test pair closer than the gap, a block shared between splits, a train event after the cut-off or a test event on/before it, a background sample inside an event buffer, or duplicate ids. Tests also corrupt a table on purpose to prove each check fires.

## Manifest
`dataset_schema_version`, `feature_schema_version`, `code_version`, SHA-256 of the Phase 4 and features manifests, `seed`, all parameters, counts by exclusion reason, class balance overall and per split, strata, split parameters, leakage report, static and dynamic column metadata, accuracy-parsing rules, `caveats`, warnings, `contains_synthetic_data`, `events_origin` (`REAL_CATALOG` | `SYNTHETIC_FIXTURE` | `UNKNOWN`, stated by the caller, never guessed).

## Exporters
Parquet (pyarrow; refuses score-like column names), NumPy `.npz` stack (applies recorded normalisation), COG for rasters, and a PyTorch `Dataset` interface behind a lazy import that raises `OptionalDependencyMissing` because torch is not installed (and is never to be added without a separate authorization). The interface is not exercised beyond that refusal.

## Not verified
Real catalog format, date order, `location_accuracy` vocabulary, and whether 2x radius is a sensible buffer; behaviour on grids of millions of pixels (stratum pixel lists are held in memory); any statistic on real events.
