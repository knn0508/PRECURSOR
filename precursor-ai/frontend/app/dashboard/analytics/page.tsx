import { LineChart } from "lucide-react";
import { PlaceholderPage } from "@/components/dashboard/placeholder-page";

export default function AnalyticsPage() {
  return (
    <PlaceholderPage
      title="Analytics"
      icon={LineChart}
      description="Deformation time series and model diagnostics."
      emptyTitle="No analytics yet"
      emptyDescription="Time-series analysis needs processed deformation measurements. Charts will be added with that phase."
    />
  );
}
