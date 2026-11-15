export interface DisplacementStatus {
  available: boolean;
  reproduction: { issue_time: string; device: string; pixels_compared: number; nan_pattern_equal: boolean; max_abs_diff_mm: number; what: string; corr_forecast_vs_last_observed_increment?: number | null; forecast_q50_sd_mm?: number } | null;
  label: string;
  origin: string;
  source_note: string | null;
  images: string[];
  docs: string[];
  provenance: {
    model: string; issue_time: string; horizon_days: number; target: string; training_data: string; frame: string; track: string;
    orbit: string; resolution_m: number; pixels_with_estimate: number; pixels_total: number; caveat: string;
    train_period: string[]; test_period: string[];
    nisar_observation: { maturity: string; used_for_training: boolean; pair: string[] };
  } | null;
}

export interface BenchmarkRow {
  experiment: string; model: string; MAE_mm: number | null; RMSE_mm: number | null; cov80: number | null;
  onset_F1: number | null; params: number | null; "vs_best_naive_%": number | null;
}

export interface DisplacementMetrics {
  label: string;
  best_naive_mae: number;
  dl_beats_naive: boolean;
  benchmark: BenchmarkRow[];
  splits: Record<string, { n: number; issue_first: string; issue_last: string }>;
  verification: {
    primary_model: string;
    noise_floor: { zero_motion_MAE_stable_mm: number; primary_MAE_stable_mm: number; share_of_test_samples_stable: number };
    per_pixel: { n_pixels: number; share_pixels_model_better: number; median_pixel_skill_pct: number };
    ground_truth_coverage: Record<string, number | string>;
  };
}

export interface ForecastGrid {
  label: string;
  issue_time: string;
  horizon_days: number;
  unit: string;
  bounds: { west: number; south: number; east: number; north: number };
  /** True lon/lat corners TL, TR, BR, BL of the UTM grid. */
  corners: [number, number][];
  height: number;
  width: number;
  bands: Record<"q10_mm" | "q50_mm" | "q90_mm", (number | null)[][]>;
  no_estimate_share: number;
}
