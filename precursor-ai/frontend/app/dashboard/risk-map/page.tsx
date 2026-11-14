import { Map } from "lucide-react";
import { PlaceholderPage } from "@/components/dashboard/placeholder-page";

export default function RiskMapPage() {
  return (
    <PlaceholderPage
      title="Risk Map"
      icon={Map}
      description="Geospatial view of deformation and risk layers."
      emptyTitle="No risk layers available"
      emptyDescription="Risk layers require processed InSAR deformation data and a validated model. Neither exists yet."
    />
  );
}
