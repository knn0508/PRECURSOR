# Time-series methodology (Phase 6)

Implemented in `backend/app/services/timeseries/` and verified only on SYNTHETIC or hand-made data (2026-11-15). `REAL_DATA_VALIDATION: NOT_PERFORMED`. Statistical **description** of observed values: no forecast, no extrapolation, no rainfall alert threshold, no risk label. Design choice for the library: [ADR-0010](../adr/ADR-0010-time-series-with-scipy-no-statsmodels.md).

## Series model
`TimeSeries(kind, zone, points)`; each `SeriesPoint` keeps time (timezone-aware), value (None = missing; NaN is normalised to None), source, sensor, synthetic flag, quality, track, orbit direction, look direction. Kinds: `los_displacement_mm`, `los_velocity_mm_yr`, `coherence`, `rainfall_mm_day`, `soil_moisture`. Construction refuses: unsorted or duplicate times (no silent reordering), naive times, unknown kinds, **mixed sensors**, and for LOS/coherence kinds **mixed or unknown (orbit direction, track, look direction)**: ascending and descending are never merged and no decomposition is implemented. Stored as JSON under `data/processed/timeseries/<area_id>/<zone>/<kind>.json` (no DB table, as in Phase 5).

## Where series come from
- Rainfall: `adapters.from_rainfall_daily` takes the Phase 4 daily records (dates at midnight UTC, missing stays missing).
- Other AOI series (for example SMAP): `adapters.from_values_by_date`.
- InSAR: Phase 3 yields independent interferogram **pairs**, not a displacement time series (no SBAS/time-series inversion exists). `adapters.from_insar_pair_velocities` places each pair's mean LOS velocity at its mid-time; overlapping pairs share acquisitions, so points are **not independent** (stored in the series notes). A cumulative displacement series is not derivable today.

## Limitations report (`limitations.py`)
n points, n valid, missing fraction, span, median and maximum interval between valid observations, interval coefficient of variation, gaps (interval > `gap_factor` x median; factor is a caller choice, default 2), and aliasing: `POSSIBLE` when 2 x median interval exceeds a caller-given shortest period of interest, else `NOT_INDICATED`; `NOT_ASSESSED` without that input. Gaps are reported, never filled or interpolated. No gap-filling option exists.

## Indicators (`indicators.py`; t in days, slopes per year = x 365.25)
| Indicator | Formula / method | Minimum valid N |
|---|---|---|
| Linear trend | OLS y = a + b t; CI b +/- t(1-alpha/2, n-2) SE(b) | 5 |
| Theil-Sen | median of pairwise slopes, scipy confidence bounds | 5 |
| Mann-Kendall | S = sum sign(y_j - y_i); Var(S) = [n(n-1)(2n+5) - sum_g t_g(t_g-1)(2t_g+5)]/18; Z = (S - sign S)/sqrt(Var); order only, spacing ignored | 10 |
| Velocity change | difference of the OLS slopes of two windows split at a given day; CI from the combined standard error, t with n1+n2-4 df | 5 per window |
| Acceleration | quadratic OLS in centred years, a = 2 c2 (units/yr^2), t-interval | **8** |
| Antecedent sums | trailing 1/3/7/14/30-day accumulation incl. the day; NaN if any day of the window is missing (never a partial sum) | complete daily calendar |
| API | API_t = k API_(t-1) + P_t, k in (0, 1) caller-supplied; first ceil(ln 0.01 / ln k) days (initial state weighs < 1%) and every restart after a missing day are NaN | complete daily calendar |
| Wet spells | maximal runs of days with P >= caller threshold (a definition of a wet day, for example 1 mm, **not an alert level**); count, duration, total, peak daily value, adjacency to missing days | complete daily calendar |
| Lagged correlation | Pearson r of x(d) and y(d + lag) on exact day matches only; no p-values | 10 pairs per lag |

The N values (5, 10, 8, 5, 10) are working choices, not literature-derived; below N an indicator returns `NOT_AVAILABLE` with the reason. All intervals assume independent errors; serial correlation (certain for overlapping InSAR pairs and for daily rainfall) makes them too narrow, and every output says so. Lagged correlation is descriptive: correlation is not causation, and shared seasonality can create any lag.

## Lead-time building blocks (`lead_features.py`)
`rainfall_before(series, reference, k)`: accumulation over [reference-k, reference-1] (the reference day is excluded because it may fall after the event); `value_at_lead`: latest valid observation at or before reference-k within a caller-set maximum age. NaN when missing. **The Phase 5 reserved `dyn__*__t_minus_{k}d` columns are NOT filled**: Phase 4 stores AOI-level series only, so these values would be spatially constant across dataset rows. Filling them needs per-point (gridded) rainfall, soil moisture and velocity series.

## Forecasting
Interface only: `Forecaster` protocol, `ForecastRequest`/`ForecastResult`, `NotImplementedForecaster` -> `NOT_IMPLEMENTED`, no values, no uncertainty. Trend and acceleration estimates describe the observed window; they are not forecasts, and persistence or linear extrapolation is deliberately not offered.

## Caveats carried by every result
LOS is not vertical motion; the LOS sign convention is unverified (Phase 3 issue 14); IMERG is ~0.1 degree and not real-time; SMAP is coarse (9-36 km); synthetic data is flagged in the series, the analysis and the API.
