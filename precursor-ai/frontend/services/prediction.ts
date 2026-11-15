import { apiGet, apiPost } from "@/lib/api-client";
import type {
  ExplainResponse, Head, PredictionRequest, PredictionResponse, PredictionStatus, SeriesAnalysis, SeriesList, UncertaintyReport,
} from "@/types/prediction";

export const getPredictionStatus = (s?: AbortSignal) => apiGet<PredictionStatus>("/prediction/status", { signal: s });
/** The head routes answer 200 + MODEL_NOT_TRAINED while no model is registered (not an error). */
export const predict = (head: Head, body: PredictionRequest, s?: AbortSignal) =>
  apiPost<PredictionResponse>(`/prediction/${head}`, body, { signal: s });
export const explain = (body: { area_id: string; head: Head; scope?: "global" | "local" }, s?: AbortSignal) =>
  apiPost<ExplainResponse>("/prediction/explain", body, { signal: s });
export const getUncertaintyReport = (areaId: string, s?: AbortSignal) =>
  apiGet<UncertaintyReport>(`/uncertainty/areas/${areaId}/report`, { signal: s });
export const listSeries = (areaId: string, s?: AbortSignal) => apiGet<SeriesList>(`/timeseries/areas/${areaId}/series`, { signal: s });
export const getSeriesAnalysis = (areaId: string, zone: string, kind: string, s?: AbortSignal) =>
  apiGet<SeriesAnalysis>(`/timeseries/areas/${areaId}/series/${encodeURIComponent(zone)}/${encodeURIComponent(kind)}/analysis`, { signal: s });
