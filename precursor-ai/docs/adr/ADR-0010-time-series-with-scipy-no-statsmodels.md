# ADR-0010: Phase 6 time-series statistics with scipy, no statsmodels

- Status: ACCEPTED (engineering decision, 2026-11-15; reversible)
- Context: the Phase 6 brief names statsmodels for the linear trend with a confidence interval.

## Decision
Implement the deterministic indicators with `numpy` and `scipy` (already pinned for Phase 5): OLS slope and t-interval via `scipy.stats.linregress`/`t`, Theil-Sen via `scipy.stats.theilslopes`, quadratic OLS by `numpy.linalg`, Mann-Kendall written out (tie-corrected variance, continuity-corrected Z) because scipy has no Mann-Kendall test. **No statsmodels dependency is added.**

## Why
statsmodels is large, brings pandas/patsy coupling and would force a slow backend image rebuild (Phase 5 issue 39: `--no-cache-dir` re-downloads every package) for features that are a few lines of closed-form formulas here. Every formula is hand-checked in `backend/tests/timeseries`.

## Consequences
No regression diagnostics, autocorrelation-robust errors (HAC) or seasonal decomposition. Confidence intervals assume independent errors and say so in every output. If later work needs them (for example HAC intervals for real, autocorrelated InSAR series), add statsmodels then with its own justification.

## Related
[TIME_SERIES_METHODOLOGY](../scientific/TIME_SERIES_METHODOLOGY.md), [ADR-0007](ADR-0007-feature-extraction-and-labelled-dataset.md), [PHASE_06](../phases/PHASE_06.md)
