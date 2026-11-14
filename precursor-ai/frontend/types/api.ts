// Mirrors backend Pydantic schemas (backend/app/schemas). Keep in sync.

export interface HealthResponse {
  status: "ok" | "degraded";
  app_name: string;
  version: string;
  database: "connected" | "unavailable";
}

export interface ModuleInfo {
  name: string;
  status: "available" | "planned";
  description: string;
}

export interface SystemInfo {
  app_name: string;
  version: string;
  environment: string;
  modules: ModuleInfo[];
}

export interface MonitoredArea {
  id: string;
  name: string;
  description: string | null;
  country: string | null;
  region: string | null;
  area_type: string;
  geometry: Record<string, unknown>; // GeoJSON Polygon | MultiPolygon
  created_at: string;
  updated_at: string;
}

export interface AreaList {
  items: MonitoredArea[];
  total: number;
}

export interface SatelliteAcquisition {
  id: string;
  satellite_source: string;
  area_id: string;
  acquisition_date: string;
  orbit_direction: string | null;
  polarization: string | null;
  product_type: string | null;
  processing_status: string;
}

export interface AcquisitionList {
  items: SatelliteAcquisition[];
  total: number;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}
