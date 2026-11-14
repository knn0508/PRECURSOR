import { AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { dataKindLabel, dataKindVariant, maturityVariant } from "@/lib/data-helpers";
import { cn } from "@/lib/utils";
import type { DataKind, Maturity } from "@/types/data";

export function MaturityBadge({ maturity }: { maturity: Maturity | null }) {
  return (
    <Badge variant={maturityVariant(maturity)} title={maturity && maturity !== "VALIDATED" ? "Lower product maturity" : undefined}>
      {maturity ?? "No maturity"}
    </Badge>
  );
}

export function DataKindBadge({ kind }: { kind: DataKind }) {
  return <Badge variant={dataKindVariant(kind)}>{dataKindLabel(kind)}</Badge>;
}

export function StatusBadge({ status }: { status: string }) {
  const failed = status === "FAILED" || status === "UNAVAILABLE";
  return <Badge className={cn(failed && "border-danger/40 bg-danger/10 text-danger")}>{status}</Badge>;
}

/** Visible alert block for warnings / provider errors. */
export function AlertBlock({ title, items, tone = "warn" }: { title: string; items: string[]; tone?: "warn" | "danger" }) {
  if (items.length === 0) return null;
  return (
    <div
      role="alert"
      className={cn(
        "rounded-lg border p-4 text-sm",
        tone === "danger" ? "border-danger/40 bg-danger/5" : "border-warn/40 bg-warn/5",
      )}
    >
      <p className={cn("flex items-center gap-2 font-medium", tone === "danger" ? "text-danger" : "text-warn")}>
        <AlertTriangle aria-hidden className="h-4 w-4" />
        {title}
      </p>
      <ul className="mt-1 list-disc space-y-0.5 pl-6 text-ink-muted">
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </div>
  );
}

export function Notice({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink-muted">{children}</p>;
}
