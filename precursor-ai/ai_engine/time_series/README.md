# time_series

**Future responsibility:** per-pixel/per-zone deformation time series: velocity, acceleration, trend/seasonality, anomaly detection and forecasting.

Scientific constraint: chronological ordering is mandatory. Use forward-chaining (expanding window) validation; never random k-fold across time. Compare against naive baselines (persistence, linear trend) before claiming skill.
