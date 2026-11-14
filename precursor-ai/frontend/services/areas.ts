import { apiGet } from "@/lib/api-client";
import type { AreaList, MonitoredArea } from "@/types/api";

export const listAreas = (signal?: AbortSignal) => apiGet<AreaList>("/areas", { signal });
export const getArea = (id: string, signal?: AbortSignal) => apiGet<MonitoredArea>(`/areas/${id}`, { signal });
