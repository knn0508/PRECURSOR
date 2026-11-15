import { apiGet } from "@/lib/api-client";
import { API_URL } from "@/lib/config";
import type { AreaBacktest, BacktestGrids, DisplacementMetrics, DisplacementStatus, ForecastGrid } from "@/types/displacement";

export const getDisplacementStatus = (s?: AbortSignal) => apiGet<DisplacementStatus>("/displacement-forecast/status", { signal: s });
export const getDisplacementMetrics = (s?: AbortSignal) => apiGet<DisplacementMetrics>("/displacement-forecast/metrics", { signal: s });
export const getDisplacementForecast = (s?: AbortSignal) =>
  apiGet<ForecastGrid>("/displacement-forecast/forecast", { signal: s, timeoutMs: 30000 });
export const displacementImageUrl = (name: string) => `${API_URL}/displacement-forecast/images/${encodeURIComponent(name)}`;
export const displacementDocUrl = (name: string) => `${API_URL}/displacement-forecast/docs/${encodeURIComponent(name)}`;
export const getAreaBacktest = (areaId: string, s?: AbortSignal) => apiGet<AreaBacktest>(`/displacement-forecast/areas/${areaId}/backtest`, { signal: s });
export const getBacktestGrids = (issue: string, s?: AbortSignal) =>
  apiGet<BacktestGrids>(`/displacement-forecast/backtest/${encodeURIComponent(issue)}`, { signal: s, timeoutMs: 30000 });
