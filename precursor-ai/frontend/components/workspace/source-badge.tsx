import { Badge } from "@/components/ui/badge";
import { SOURCE_META, type SourceKind } from "@/lib/source-badges";

/** One per layer/panel. Synthetic and placeholder content use the loud variant; nothing implies validation. */
export function SourceBadge({ kind }: { kind: SourceKind }) {
  const m = SOURCE_META[kind];
  // Synthetic data keeps the warning tone; placeholders use a high-contrast NEUTRAL style so mock views never carry amber/red/green.
  const cls = kind === "PLACEHOLDER" ? "border-ink text-ink" : undefined;
  return (
    <Badge variant={kind === "SYNTHETIC_DEMO" ? "demo" : "neutral"} className={cls} title={m.description} data-source-kind={kind}>
      {kind.replaceAll("_", " ")}
    </Badge>
  );
}
