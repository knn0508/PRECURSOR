import { Suspense } from "react";
import { EnvironmentalSection } from "@/components/environmental/environmental-section";

export default function EnvironmentalPage() {
  return (
    <Suspense>
      <EnvironmentalSection />
    </Suspense>
  );
}
