import { DisplacementSummary } from "@/components/workspace/displacement-summary";
import { EarlyWarningPage } from "@/components/workspace/early-warning-page";

export default function PredictionsPage() {
  return (
    <div className="space-y-6">
      <EarlyWarningPage title="Predictions" heads={["susceptibility", "trigger"]} />
      <DisplacementSummary />
    </div>
  );
}
