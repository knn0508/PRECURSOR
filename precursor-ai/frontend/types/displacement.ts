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

export interface BacktestMetrics {
  n_pixels: number; MAE_model_mm: number; MAE_zero_mm: number; MAE_ridge_mm: number; skill_vs_zero_pct: number; skill_vs_ridge_pct: number;
  cov80: number; width80_mm: number; corr_forecast_vs_last_change: number | null; corr_forecast_vs_actual: number | null; corr_actual_vs_last_change: number | null;
  MAE_diff_model_minus_zero_ci95_mm?: [number, number]; MAE_diff_model_minus_ridge_ci95_mm?: [number, number];
}
export interface BacktestDate extends BacktestMetrics { issue: string; target: string; horizon_days: number; pixels_with_forecast: number; pixels_scored: number; actual_available_pct: number }
export interface BacktestMeta {
  label: string; kind: string; device: string; model: string; frame: string; horizon_days: number; issue_dates: string[]; target_dates: string[];
  test_period: string; latest_data_date: string; held_out_note: string; no_leakage: string; scoring: string; ci_note: string;
  pooled: BacktestMetrics; per_date: BacktestDate[];
}
export interface AreaBacktest {
  area_id: string; area_name: string; label?: string; covered: boolean; area_covered_pct: number; footprint_covered_by_area_pct: number;
  result: BacktestMeta | null; reason?: string;
}
export interface BacktestGrids {
  label: string; issue: string; target: string; unit: string; corners: [number, number][]; height: number; width: number;
  forecast: { q10_mm: (number | null)[][]; q50_mm: (number | null)[][]; q90_mm: (number | null)[][] };
  actual_mm: (number | null)[][]; difference_mm: (number | null)[][]; metrics: BacktestDate;
}
