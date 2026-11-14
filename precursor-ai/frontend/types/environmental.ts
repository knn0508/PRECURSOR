// Mirrors backend/app/schemas/environmental.py. Keep in sync. No type here is a risk score or prediction.
export type DataOrigin = "REAL_SATELLITE" | "SYNTHETIC_FIXTURE" | "LOCAL_UNVERIFIED";
export type Json = Record<string, unknown>;

export interface LayerRead {
  id: string;
  area_id: string;
  run_id: string | null;
  layer_type: string;
  source_provider: string;
  dataset_name: string;
  dataset_version: string | null;
  measurement_kind: string;
  data_origin: DataOrigin;
  validation_status: string;
  status: string;
  units: string | null;
  crs: string | null;
  width: number | null;
  height: number | null;
  nodata: number | null;
  native_resolution: Json | null;
  processing_resolution: Json | null;
  temporal_start: string | null;
  temporal_end: string | null;
  footprint: unknown;
  provenance: Json;
  quality: Json;
  statistics: Json;
  temporal_kind?: "static" | "dynamic" | string;
  aligned?: boolean;
  has_raster: boolean;
  label: string;
  created_at: string;
}
export interface LayerList { items: LayerRead[]; total: number }

export interface LegendClass { id: number; name: string; color: string }
export interface LegendRead {
  layer_id: string;
  layer_type: string;
  units: string | null;
  kind: "continuous" | "circular" | "categorical" | string;
  vmin: number | null;
  vmax: number | null;
  /** hex stops, low to high, identical to the server-rendered preview PNG ramp */
  colors?: string[];
  classes: LegendClass[];
  note: string;
}

export interface CoverageItem {
  layer_type: string;
  available: boolean;
  status: string;
  data_origin: DataOrigin | null;
  valid_percent: number | null;
  missing_percent: number | null;
  aoi_coverage_percent: number | null;
  temporal_start: string | null;
  temporal_end: string | null;
  layer_id: string | null;
  reason: string | null;
}
export interface CoverageRead {
  area_id: string;
  items: CoverageItem[];
  missing_datasets: string[];
  last_processed_at: string | null;
  note: string;
}

export interface ProcessConfig {
  stages?: string[] | null;
  force?: boolean;
  start_date?: string | null;
  end_date?: string | null;
  rolling_windows?: number[];
  include_insar?: boolean;
  grid_crs?: string | null;
  grid_resolution_m?: number | null;
  rainfall_resolution?: "daily" | "half_hourly";
}

export interface StageRead { name: string; status: string; message: string | null; started_at: string | null; ended_at: string | null }
export interface RunSummary {
  id: string;
  area_id: string;
  status: string;
  current_stage: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}
export interface RunRead extends RunSummary { stages: StageRead[]; config: Json; warnings: string[] }
export interface RunList { items: RunSummary[]; total: number }
export interface RunCreateResponse { run: RunSummary }

export interface FeatureRead {
  group: string;
  status: string;
  values: Record<string, unknown>;
  units: Record<string, string>;
  lineage: Json[];
  measurement_kind: string;
  data_origin: DataOrigin;
  warnings: string[];
  label: string;
}
export interface FeaturesRead { area_id: string; run_id: string | null; groups: FeatureRead[]; disclaimer: string }

export interface RainfallPoint { date: string; precipitation_mm: number | null; observed: boolean }
export interface RainfallRead {
  area_id: string;
  status: string;
  data_origin: DataOrigin | null;
  source: string | null;
  temporal_start: string | null;
  temporal_end: string | null;
  units: string;
  quantity: string;
  daily: RainfallPoint[];
  monthly: RainfallPoint[];
  rolling: Record<string, RainfallPoint[]>;
  observed_days: number;
  missing_days: number;
  notes: string[];
}

export interface EventsRead {
  area_id: string;
  status: string;
  total: number;
  geojson: { type?: string; features?: EventFeature[] } & Json;
  summary: Json;
  limitations: string[];
}
export interface EventFeature { type: "Feature"; geometry: { type: string; coordinates: unknown } | null; properties: Json | null }

export interface SeismicRefreshRequest { start_date: string; end_date: string; min_magnitude?: number | null }
export interface SeismicRefreshResponse { area_id: string; fetched: number; inserted: number; duplicates: number; warnings: string[] }

export interface QualityReportRead { area_id: string; run_id: string | null; report: Json }

export interface DatasetInfo {
  layer_type: string;
  provider: string;
  dataset_name: string;
  implementation_status: string;
  description: string;
  native_resolution: string | null;
  temporal_resolution: string | null;
  units: string | null;
  access: string | null;
  license: string | null;
  limitations: string[];
}
export interface DatasetList { items: DatasetInfo[] }

export interface ManifestEntry {
  layer_id: string | null;
  layer_type: string;
  kind: "raster" | "series" | "vector" | string;
  temporal_kind: "static" | "dynamic" | string;
  status: string;
  units: string | null;
  crs: string | null;
  native_resolution: Json | null;
  processing_resolution: Json | null;
  on_reference_grid: boolean;
  source: Json; // provider, dataset_name, dataset_version
  temporal_start: string | null;
  temporal_end: string | null;
  data_origin: DataOrigin | null;
  synthetic: boolean;
  validation_status: string;
  nodata: number | null;
  coverage: Json; // valid_percent, missing_percent, aoi_coverage_percent
  provenance: Json;
  lineage_hash: string | null;
  input_hash: string | null;
  file: string | null; // name only
  reason: string | null;
}
export interface ManifestRead {
  area_id: string;
  run_id: string | null;
  generated_at: string;
  reference_grid: Json | null;
  entries: ManifestEntry[];
  counts: Record<string, number>;
  contains_synthetic_data: boolean;
  validation_status: string;
  real_data_validation: string;
  notes: string[];
}
