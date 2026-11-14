import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <Card className="flex flex-col items-center justify-center border-dashed px-6 py-14 text-center">
      <div className="mb-4 rounded-full border border-line bg-surface-2 p-3">
        <Icon aria-hidden className="h-6 w-6 text-ink-muted" />
      </div>
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mt-1 max-w-md text-sm text-ink-muted">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </Card>
  );
}
