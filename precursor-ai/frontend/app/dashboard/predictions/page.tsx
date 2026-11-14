import { Activity } from "lucide-react";
import { PlaceholderPage } from "@/components/dashboard/placeholder-page";

export default function PredictionsPage() {
  return (
    <PlaceholderPage
      title="Predictions"
      icon={Activity}
      description="Model-estimated landslide risk with uncertainty."
      emptyTitle="No predictions available"
      emptyDescription="No model has been trained or validated. Predictions will appear here with explicit uncertainty once they exist."
    />
  );
}
