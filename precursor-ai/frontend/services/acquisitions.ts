import { apiGet } from "@/lib/api-client";
import type { AcquisitionList } from "@/types/api";

export const listAcquisitions = (limit = 5, signal?: AbortSignal) =>
  apiGet<AcquisitionList>(`/acquisitions?limit=${limit}`, { signal });
