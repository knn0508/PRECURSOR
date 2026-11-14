import { Settings } from "lucide-react";
import { PlaceholderPage } from "@/components/dashboard/placeholder-page";

export default function SettingsPage() {
  return (
    <PlaceholderPage
      title="Settings"
      icon={Settings}
      description="Platform and display preferences."
      emptyTitle="No configurable settings yet"
      emptyDescription="Preferences will be added as features need them."
    />
  );
}
