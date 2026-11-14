import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  /** null renders an explicit "not available" state rather than a made-up number. */
  value: number | string | null;
  icon: LucideIcon;
  hint?: string;
  tone?: "default" | "danger" | "warn" | "ok";
}

const TONES = { default: "text-accent", danger: "text-danger", warn: "text-warn", ok: "text-ok" };

export function StatCard({ label, value, icon: Icon, hint, tone = "default" }: StatCardProps) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">{label}</p>
        <Icon aria-hidden className={cn("h-4 w-4", TONES[tone])} />
      </div>
      <p className="mt-3 font-mono text-3xl font-semibold tabular-nums text-ink">{value ?? "N/A"}</p>
      {hint && <p className="mt-1 text-xs text-ink-faint">{hint}</p>}
    </Card>
  );
}
