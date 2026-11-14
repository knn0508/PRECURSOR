import { apiGet, apiPost, buildQuery } from "@/lib/api-client";
import type {
  AcquisitionList, AcquisitionStatus, CollectionRead, DataStatus, DownloadCreateResponse, DownloadJobList,
  DownloadJobRead, EnvironmentalAcquireRequest, EnvironmentalAcquireResponse, JobStatus, LandslideEventList,
  LandslideImportRequest, LandslideImportResponse, Maturity, SearchRequest, SearchResponse,
} from "@/types/data";

export const getDataStatus = (signal?: AbortSignal) => apiGet<DataStatus>("/data/status", { signal });

export const listCollections = (q: { provider?: string; refresh?: boolean } = {}, signal?: AbortSignal) =>
  apiGet<CollectionRead[]>(`/data/collections${buildQuery(q)}`, { signal });

export interface AcquisitionFilters {
  monitored_area_id?: string;
  product_type?: string;
  status?: AcquisitionStatus | "";
  maturity?: Maturity | "";
  start_date?: string;
  end_date?: string;
  offset?: number;
  limit?: number;
}
export const listDataAcquisitions = (q: AcquisitionFilters = {}, signal?: AbortSignal) =>
  apiGet<AcquisitionList>(`/data/acquisitions${buildQuery({ ...q })}`, { signal });

// Search/acquire hit CMR upstream, so they get a longer timeout than the default 8 s.
export const searchData = (body: SearchRequest, signal?: AbortSignal) =>
  apiPost<SearchResponse>("/data/search", body, { signal, timeoutMs: 60_000 });

export const createDownloads = (acquisition_ids: string[], signal?: AbortSignal) =>
  apiPost<DownloadCreateResponse>("/data/downloads", { acquisition_ids }, { signal });

export const listDownloads = (
  q: { status?: JobStatus | ""; offset?: number; limit?: number } = {},
  signal?: AbortSignal,
) => apiGet<DownloadJobList>(`/data/downloads${buildQuery(q)}`, { signal });

export const getDownload = (id: string, signal?: AbortSignal) =>
  apiGet<DownloadJobRead>(`/data/downloads/${id}`, { signal });

export const retryDownload = (id: string, signal?: AbortSignal) =>
  apiPost<DownloadJobRead>(`/data/downloads/${id}/retry`, {}, { signal });

export const acquireEnvironmental = (body: EnvironmentalAcquireRequest, signal?: AbortSignal) =>
  apiPost<EnvironmentalAcquireResponse>("/data/environmental/acquire", body, { signal, timeoutMs: 60_000 });

export const listLandslideEvents = (q: { offset?: number; limit?: number } = {}, signal?: AbortSignal) =>
  apiGet<LandslideEventList>(`/data/landslide-events${buildQuery(q)}`, { signal });

export const importLandslideEvents = (body: LandslideImportRequest = { force: false }, signal?: AbortSignal) =>
  apiPost<LandslideImportResponse>("/data/landslide-events/import", body, { signal, timeoutMs: 120_000 });
