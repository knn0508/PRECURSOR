"""Forecasting INTERFACE only (Phase 6). No forecaster exists: persistence or linear extrapolation is NOT presented as a forecast,
and ML forecasting is out of scope (ADR-0002). `NotImplementedForecaster` always answers NOT_IMPLEMENTED."""
from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ForecastRequest(BaseModel):
    kind: str
    zone: str
    horizon_days: int = Field(gt=0)


class ForecastResult(BaseModel):
    status: Literal["NOT_IMPLEMENTED", "OK"]
    message: str
    horizon_days: int
    values: list[float] | None = None  # always None while NOT_IMPLEMENTED
    uncertainty: dict | None = None  # must come from a real method; None until one exists


@runtime_checkable
class Forecaster(Protocol):
    def forecast(self, series, request: ForecastRequest) -> ForecastResult: ...


class NotImplementedForecaster:
    def forecast(self, series, request: ForecastRequest) -> ForecastResult:
        return ForecastResult(status="NOT_IMPLEMENTED", horizon_days=request.horizon_days,
                              message="No forecasting method exists. Trend indicators describe observed data and are not forecasts.")
