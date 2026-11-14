import type { LucideIcon } from "lucide-react";
import { EmptyState } from "@/components/dashboard/empty-state";
import { Badge } from "@/components/ui/badge";

interface PlaceholderPageProps {
  title: string;
  icon: LucideIcon;
  description: string;
  emptyTitle: string;
  emptyDescription: string;
}

export function PlaceholderPage({ title, icon, description, emptyTitle, emptyDescription }: PlaceholderPageProps) {
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">{title}</h1>
          <Badge>Planned</Badge>
        </div>
        <p className="mt-1 text-sm text-ink-muted">{description}</p>
      </div>
      <EmptyState icon={icon} title={emptyTitle} description={emptyDescription} />
    </div>
  );
}
