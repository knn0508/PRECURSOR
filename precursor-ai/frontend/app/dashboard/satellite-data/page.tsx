import { Database } from "lucide-react";
import { PlaceholderPage } from "@/components/dashboard/placeholder-page";

export default function SatelliteDataPage() {
  return (
    <PlaceholderPage
      title="Satellite Data"
      icon={Database}
      description="Catalog of Sentinel-1 and NISAR acquisitions."
      emptyTitle="No satellite data ingested"
      emptyDescription="Data acquisition is a later phase. Acquisitions will be listed here once ingested."
    />
  );
}
