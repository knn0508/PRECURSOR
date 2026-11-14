import { apiGet } from "@/lib/api-client";
import type { HealthResponse, SystemInfo } from "@/types/api";

export const getHealth = (signal?: AbortSignal) => apiGet<HealthResponse>("/health", { signal });
export const getSystemInfo = (signal?: AbortSignal) => apiGet<SystemInfo>("/system/info", { signal });
