import { Bell } from "lucide-react";
import { PlaceholderPage } from "@/components/dashboard/placeholder-page";

export default function AlertsPage() {
  return (
    <PlaceholderPage
      title="Alerts"
      icon={Bell}
      description="Notifications when monitored areas change."
      emptyTitle="No alerts"
      emptyDescription="Alerting depends on risk assessment, which is not implemented yet."
    />
  );
}
