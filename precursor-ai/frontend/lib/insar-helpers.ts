import type { DataOrigin, DeformationType, RunStatus, RunSummary } from "@/types/insar";

export const INSAR_DISCLAIMER =
  "Measures line-of-sight (LOS) ground motion from already-downloaded SAR products. It is not a landslide risk map or prediction, and no real-satellite scientific validation has been performed.";

const TERMINAL: RunStatus[] = ["COMPLETED", "FAILED", "CANCELLED", "BLOCKED_MISSING_INPUT"];
export const isTerminal = (s: RunStatus) => TERMINAL.includes(s);
export const hasActiveRuns = (runs: Pick<RunSummary, "status">[]) => runs.some((r) => !isTerminal(r.status));

/** Blocked input is not a processing failure; they are shown differently. */
export const statusTone = (s: RunStatus): "ok" | "danger" | "warn" | "accent" =>
  s === "COMPLETED" ? "ok" : s === "FAILED" ? "danger" : s === "BLOCKED_MISSING_INPUT" || s === "CANCELLED" ? "warn" : "accent";

export const statusLabel = (s: RunStatus) =>
  s === "BLOCKED_MISSING_INPUT" ? "Blocked: input or tool missing" : s.replaceAll("_", " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());

export const originLabel = (o: DataOrigin | null | undefined): string =>
  o === "SYNTHETIC_FIXTURE"
    ? "SYNTHETIC TEST DATA: not a satellite observation"
    : o === "REAL_SATELLITE"
      ? "Derived from registered satellite data; not scientifically validated"
      : o === "LOCAL_UNVERIFIED"
        ? "Local file of unverified provenance; not scientifically validated"
        : "Origin not yet determined";

export const isSynthetic = (o: DataOrigin | null | undefined) => o === "SYNTHETIC_FIXTURE";

export const PRODUCT_LABEL: Record<DeformationType, string> = {
  LOS_DISPLACEMENT: "LOS displacement",
  COHERENCE: "Coherence",
  LOS_VELOCITY: "LOS velocity (mean over the interferogram baseline)",
};

/** "" -> null (no coherence masking). Anything outside 0..1 or non-numeric is invalid (undefined). */
export function parseThreshold(raw: string): number | null | undefined {
  const t = raw.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 && n <= 1 ? n : undefined;
}

export function formatStat(v: number | string | null | undefined, unit: string): string {
  if (v === null || v === undefined || typeof v === "string") return "n/a";
  const a = Math.abs(v);
  const s = a !== 0 && (a < 0.01 || a >= 1e5) ? v.toExponential(2) : v.toFixed(a >= 100 ? 1 : 3);
  return `${s} ${unit}`;
}
