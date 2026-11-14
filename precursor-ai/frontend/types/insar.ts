// Mirrors backend/app/schemas/insar.py. Keep in sync.
export type DataOrigin = "REAL_SATELLITE" | "SYNTHETIC_FIXTURE" | "LOCAL_UNVERIFIED";
export type RunStatus =
  | "PENDING" | "QUEUED" | "INSPECTING" | "PREPROCESSING" | "INTERFEROGRAM_GENERATION" | "PHASE_UNWRAPPING"
  | "DISPLACEMENT_CALCULATION" | "QUALITY_CHECK" | "COMPLETED" | "FAILED" | "CANCELLED" | "BLOCKED_MISSING_INPUT";
export type DeformationType = "LOS_DISPLACEMENT" | "COHERENCE" | "LOS_VELOCITY";

export interface ProcessableProduct {
  id: string; // acquisition uuid or "sample:<file>"
  source: "ACQUISITION" | "SAMPLE";
  name: string;
  product_type: string;
  data_origin_hint: string;
  size_bytes: number | null;
  acquisition_start: string | null;
  maturity: string | null;
}
export interface ProductList { items: ProcessableProduct[]; note: string }

export interface InspectionReport {
  file_name: string;
  file_size_bytes: number;
  file_format: string;
  product_kind: string;
  data_origin: DataOrigin;
  product_version: string | null;
  orbit_direction: string | null;
  wavelength_m: number | null;
  reference_time: string | null;
  secondary_time: string | null;
  missing: string[];
  warnings: string[];
  supported_stages: string[];
  displacement_supported: boolean;
  displacement_blockers: string[];
}

export interface StageRead { name: string; status: string; message: string | null; started_at: string | null; ended_at: string | null }

export interface RunSummary {
  id: string;
  acquisition_id: string | null;
  input_kind: string;
  input_ref: string;
  product_kind: string | null;
  data_origin: DataOrigin | null;
  status: RunStatus;
  current_stage: string | null;
  progress: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}
export interface RunList { items: RunSummary[]; total: number }

export interface DeformationRead {
  id: string;
  run_id: string;
  product_type: DeformationType;
  units: string;
  crs: string | null;
  width: number;
  height: number;
  reference_time: string | null;
  secondary_time: string | null;
  data_origin: DataOrigin;
  sign_convention: string | null;
  scientifically_validated: boolean;
  statistics: Record<string, number | string | null>;
  label: string;
  file_size_bytes: number | null;
}

export interface RunRead extends RunSummary {
  stages: StageRead[];
  config: Record<string, unknown>;
  warnings: string[];
  products: DeformationRead[];
}

export interface QualityReport {
  status: string;
  label: string;
  data_origin: DataOrigin;
  real_satellite_data: boolean;
  real_data_validation: string;
  scientifically_validated: boolean;
  sign_convention: string;
  sign_convention_verified: boolean;
  limitations: string[];
  warnings: string[];
  errors: string[];
}

export interface ProcessingConfigIn {
  polarization?: string | null;
  coherence_threshold?: number | null;
  use_connected_components_mask?: boolean;
  compute_velocity?: boolean;
}
export interface RunCreateResponse { run: RunSummary; created: boolean }
