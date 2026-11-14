import { AlertTriangle, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ title = "Something went wrong", message, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-lg border border-danger/30 bg-danger/5 p-4">
      <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-ink">{title}</p>
        <p className="mt-0.5 text-sm text-ink-muted">{message}</p>
      </div>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          <RotateCw aria-hidden className="h-3.5 w-3.5" />
          Retry
        </Button>
      )}
    </div>
  );
}
