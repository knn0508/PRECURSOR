import { EarlyWarningPage } from "@/components/workspace/early-warning-page";
import { SusceptibilityTrackStatus } from "@/components/workspace/susceptibility-track-status";

export default function RiskMapPage() {
  return (
    <div className="space-y-6">
      <EarlyWarningPage title="Susceptibility map" heads={["susceptibility"]} />
      <SusceptibilityTrackStatus />
    </div>
  );
}
