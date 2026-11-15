import type { PredictionResponse } from "@/types/prediction";

export type EarlyWarningView = "NA" | "MOCK" | "REAL";

export const RESEARCH_NOTICE = "Research prototype, not an official warning. Do not use for evacuation, safety or operational decisions.";
export const NA_TEXT = "N/A until a real, validated source exists";

/**
 * Which view to show. The REAL view activates by itself as soon as the API answers OK with an output (no flag needed, no route change);
 * MOCK appears only when the API says MODEL_NOT_TRAINED AND the build flag is on; otherwise N/A. An error or loading state is not a view.
 */
export function resolveView(response: PredictionResponse | null, mockFlag: boolean): EarlyWarningView {
  if (response && response.status === "OK" && response.output) return "REAL";
  return mockFlag ? "MOCK" : "NA";
}

/** Probability formatted for display; the unit is "model output" until calibration is stated in the response. */
export const formatProbability = (p: number) => `${(p * 100).toFixed(1)}%`;
