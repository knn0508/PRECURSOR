import { apiGet, apiPost, buildQuery } from "@/lib/api-client";
import { API_URL } from "@/lib/config";
import type {
  CoverageRead, DatasetList, EventsRead, FeatureRead, FeaturesRead, LayerList, LegendRead, ManifestRead, ProcessConfig,
  QualityReportRead, RainfallRead, RunCreateResponse, RunList, RunRead, SeismicRefreshRequest, SeismicRefreshResponse,
} from "@/types/environmental";

const A = (id: string) => `/environmental/areas/${id}`;

export const listDatasets = (s?: AbortSignal) => apiGet<DatasetList>("/environmental/datasets", { signal: s });
export const getLayers = (id: string, s?: AbortSignal) => apiGet<LayerList>(`${A(id)}/layers`, { signal: s });
export const getCoverage = (id: string, s?: AbortSignal) => apiGet<CoverageRead>(`${A(id)}/coverage`, { signal: s });
/** Areas are referenced by id only; the API never accepts a filesystem path. */
export const startProcessing = (id: string, config: ProcessConfig, s?: AbortSignal) =>
  apiPost<RunCreateResponse>(`${A(id)}/process`, config, { signal: s });
export const listRuns = (q: { area_id?: string; status?: string } = {}, s?: AbortSignal) =>
  apiGet<RunList>(`/environmental/processing-runs${buildQuery(q)}`, { signal: s });
export const getRun = (id: string, s?: AbortSignal) => apiGet<RunRead>(`/environmental/processing-runs/${id}`, { signal: s });
export const getTerrain = (id: string, s?: AbortSignal) => apiGet<FeatureRead>(`${A(id)}/terrain`, { signal: s });
export const getRainfall = (id: string, s?: AbortSignal) => apiGet<RainfallRead>(`${A(id)}/rainfall`, { signal: s });
export const getSoil = (id: string, s?: AbortSignal) => apiGet<FeatureRead>(`${A(id)}/soil`, { signal: s });
export const getLandCover = (id: string, s?: AbortSignal) => apiGet<FeatureRead>(`${A(id)}/land-cover`, { signal: s });
export const getLandslides = (id: string, s?: AbortSignal) =>
  apiGet<EventsRead>(`${A(id)}/historical-landslides`, { signal: s });
export const getSeismic = (id: string, s?: AbortSignal) => apiGet<EventsRead>(`${A(id)}/seismic`, { signal: s });
export const getManifest = (id: string, s?: AbortSignal) => apiGet<ManifestRead>(`${A(id)}/manifest`, { signal: s });
export const getFeatures = (id: string, s?: AbortSignal) => apiGet<FeaturesRead>(`${A(id)}/features`, { signal: s });
export const getQualityReport = (id: string, s?: AbortSignal) =>
  apiGet<QualityReportRead>(`${A(id)}/quality-report`, { signal: s });
export const refreshSeismic = (id: string, body: SeismicRefreshRequest, s?: AbortSignal) =>
  apiPost<SeismicRefreshResponse>(`${A(id)}/seismic/refresh`, body, { signal: s, timeoutMs: 60_000 });
export const getLegend = (layerId: string, s?: AbortSignal) =>
  apiGet<LegendRead>(`/environmental/layers/${layerId}/legend`, { signal: s });

/** Browser-loadable URLs, by layer id only. */
export const layerPreviewUrl = (layerId: string) => `${API_URL}/environmental/layers/${layerId}/preview`;
export const layerRasterUrl = (layerId: string) => `${API_URL}/environmental/layers/${layerId}/raster`;
