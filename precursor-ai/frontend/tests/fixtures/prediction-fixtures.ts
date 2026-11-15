// TEST_FIXTURE: hand-made API responses used ONLY by tests to exercise the real-response path. Not a model output, not shipped to the app.
import type { ExplainResponse, PredictionResponse } from "@/types/prediction";

export const TEST_FIXTURE = "TEST_FIXTURE";
const AREA = "00000000-0000-0000-0000-000000000001";

export const NOT_TRAINED: PredictionResponse = {
  status: "MODEL_NOT_TRAINED", backend: "none", head: "susceptibility", output: null,
  message: "No model is trained or registered. This is not a prediction and not a risk assessment.",
};

export const OK_RESPONSE: PredictionResponse = {
  status: "OK", backend: "registered_model", head: "susceptibility", message: "model output",
  output: {
    model_id: TEST_FIXTURE, model_version: "0.0.0", head: "susceptibility", area_id: AREA, probability: 0.5, risk_class: "TEST_FIXTURE_CLASS",
    calibration: { calibrated: false, method: null, reference: null }, uncertainty: null, training_data_provenance: { inventory: TEST_FIXTURE },
    valid_region: { type: "Polygon", coordinates: [] }, valid_time: { start: "2020-01-01T00:00:00Z", end: null }, reference_time: null, horizon_days: null,
  },
};

export const EXPLAIN_OK: ExplainResponse = {
  status: "OK", message: "explanation of model behaviour (not causal)",
  explanation: { model_id: TEST_FIXTURE, model_version: "0.0.0", head: "susceptibility", scope: "global", method: TEST_FIXTURE, background_dataset_ref: TEST_FIXTURE,
    contributions: [{ feature: "test_feature", contribution: 0.1, units: null }], cell: null, caveats: ["Describes model behaviour, not physical causation."] },
};
