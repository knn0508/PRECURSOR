// Mirrors backend/app/schemas/prediction.py and uncertainty.py (Phases 7-8). No model exists: under the default backend every
// prediction response is MODEL_NOT_TRAINED with output = null and every explanation is MODEL_NOT_AVAILABLE.
export type Head = "susceptibility" | "trigger";
export type PredictionState = "MODEL_NOT_TRAINED" | "OK";

export interface CalibrationInfo { calibrated: boolean; method: string | null; reference: string | null }
export interface ValidTime { start: string; end: string | null }

export interface RiskModelOutput {
  model_id: string;
  model_version: string;
  head: Head;
  area_id: string;
  probability: number;
  risk_class: string | null;
  calibration: CalibrationInfo;
  uncertainty: Record<string, unknown> | null;
  training_data_provenance: Record<string, unknown>;
  valid_region: Record<string, unknown>;
  valid_time: ValidTime;
  reference_time: string | null;
  horizon_days: number | null;
}

export interface PredictionResponse {
  status: PredictionState;
  backend: string;
  head: Head;
  message: string;
  output: RiskModelOutput | null;
}

export interface PredictionStatus {
  backend: string;
  status: PredictionState;
  registered_models: number;
  refused_models: number;
  message: string;
}

export interface PredictionRequest { area_id: string; reference_time?: string | null; horizon_days?: number | null }

export interface FeatureContribution { feature: string; contribution: number; units: string | null }
export interface Explanation {
  model_id: string;
  model_version: string;
  head: Head;
  scope: "global" | "local";
  method: string;
  background_dataset_ref: string;
  contributions: FeatureContribution[];
  cell: Record<string, number> | null;
  caveats: string[];
}
export interface ExplainResponse { status: "MODEL_NOT_AVAILABLE" | "OK"; message: string; explanation: Explanation | null }

export interface UncertaintyItem { code: string; source_phase: number; severity: "INFO" | "WARNING" | "LIMITATION"; message: string; value: number | null }
export interface UncertaintyReport {
  area_id: string;
  items: UncertaintyItem[];
  predictive_uncertainty: "NOT_ESTIMATED";
  suppressed: boolean;
  suppression_reasons: { code: string; message: string }[];
  notes: string[];
}

export interface SeriesMeta {
  kind: string;
  units: string;
  zone: string;
  sensor: string;
  sources: string[];
  orbit_direction: string | null;
  track: number | null;
  first_time: string;
  last_time: string;
  contains_synthetic_data: boolean;
  real_data_validation: string;
}
export interface SeriesList { series: SeriesMeta[] }
export interface SeriesAnalysis {
  series: SeriesMeta;
  limitations: Record<string, unknown>;
  indicators: Record<string, Record<string, unknown>>;
  notes: string[];
  contains_synthetic_data: boolean;
  real_data_validation: string;
}
