import { apiGet, apiPost, buildQuery } from "@/lib/api-client";
import { API_URL } from "@/lib/config";
import type {
  InspectionReport, ProcessingConfigIn, ProductList, QualityReport, RunCreateResponse, RunList, RunRead,
} from "@/types/insar";

export const listInsarProducts = (signal?: AbortSignal) => apiGet<ProductList>("/insar/products", { signal });

/** Inputs are ids or bare sample names, never filesystem paths. */
export interface InputRef { acquisition_id?: string; sample_file?: string }

export const inspectInsarProduct = (ref: InputRef, signal?: AbortSignal) =>
  apiPost<InspectionReport>("/insar/inspect", ref, { signal, timeoutMs: 30_000 });

export const createInsarRun = (ref: InputRef, config: ProcessingConfigIn, signal?: AbortSignal) =>
  apiPost<RunCreateResponse>("/insar/processing-runs", { ...ref, config }, { signal });

export const listInsarRuns = (q: { status?: string; offset?: number; limit?: number } = {}, signal?: AbortSignal) =>
  apiGet<RunList>(`/insar/processing-runs${buildQuery(q)}`, { signal });

export const getInsarRun = (id: string, signal?: AbortSignal) => apiGet<RunRead>(`/insar/processing-runs/${id}`, { signal });

export const getInsarQuality = (id: string, signal?: AbortSignal) =>
  apiGet<QualityReport>(`/insar/processing-runs/${id}/quality`, { signal });

export const cancelInsarRun = (id: string, signal?: AbortSignal) =>
  apiPost<unknown>(`/insar/processing-runs/${id}/cancel`, {}, { signal });

/** Browser-loadable URLs (served by id only; the API never accepts a path). */
export const previewUrl = (productId: string) => `${API_URL}/insar/deformation-products/${productId}/preview`;
export const rasterUrl = (productId: string) => `${API_URL}/insar/deformation-products/${productId}/raster`;
