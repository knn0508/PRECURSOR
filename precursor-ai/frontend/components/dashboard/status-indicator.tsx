import { cn } from "@/lib/utils";

export type Status = "ok" | "degraded" | "down" | "loading";

const STYLES: Record<Status, { dot: string; text: string }> = {
  ok: { dot: "bg-ok", text: "text-ok" },
  degraded: { dot: "bg-warn", text: "text-warn" },
  down: { dot: "bg-danger", text: "text-danger" },
  loading: { dot: "bg-ink-faint animate-pulse", text: "text-ink-muted" },
};

export function StatusIndicator({ status, label, className }: { status: Status; label: string; className?: string }) {
  const s = STYLES[status];
  return (
    <span role="status" className={cn("inline-flex items-center gap-2 text-xs font-medium", s.text, className)}>
      <span aria-hidden className={cn("h-2 w-2 rounded-full", s.dot)} />
      {label}
    </span>
  );
}
