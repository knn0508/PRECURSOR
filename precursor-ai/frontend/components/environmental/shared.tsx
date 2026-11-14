import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { needsWarning, originBadge, originNote } from "@/lib/environmental-helpers";
import type { DataOrigin } from "@/types/environmental";

export function OriginBadge({ origin }: { origin: DataOrigin | null | undefined }) {
  const b = originBadge(origin);
  return <Badge variant={b.tone === "warn" ? "demo" : "neutral"}>{b.text}</Badge>;
}

/** Loud amber banner for synthetic/unverified data; quiet muted line otherwise. */
export function OriginBanner({ origin, className }: { origin: DataOrigin | null | undefined; className?: string }) {
  const warn = needsWarning(origin);
  return (
    <p
      role={warn ? "alert" : undefined}
      className={cn(
        warn ? "rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-sm font-semibold text-warn" : "text-xs text-ink-muted",
        className,
      )}
    >
      {originNote(origin)}
    </p>
  );
}

export function ToneBadge({ tone, children }: { tone: "ok" | "warn" | "danger" | "accent" | "neutral"; children: React.ReactNode }) {
  return (
    <Badge
      variant={tone === "ok" ? "ok" : tone === "accent" ? "accent" : tone === "warn" ? "demo" : "neutral"}
      className={tone === "danger" ? "border-danger/40 bg-danger/10 text-danger" : undefined}
    >
      {children}
    </Badge>
  );
}

export const layerStatusTone = (s: string): "ok" | "warn" | "danger" | "neutral" =>
  s === "PROCESSED" ? "ok" : s === "PARTIALLY_PROCESSED" ? "warn" : s === "FAILED" ? "danger" : "neutral";
