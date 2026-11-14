import { cn } from "@/lib/utils";

export function LoadingState({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <div role="status" aria-live="polite" className={cn("space-y-2", className)}>
      <span className="sr-only">{label}</span>
      <div className="h-4 w-2/3 animate-pulse rounded bg-surface-2" />
      <div className="h-4 w-1/2 animate-pulse rounded bg-surface-2" />
      <div className="h-4 w-3/5 animate-pulse rounded bg-surface-2" />
    </div>
  );
}
