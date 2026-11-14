import type { AOIInput, DataKind, DownloadJobRead, Maturity } from "@/types/data";

export const IMERG_NOTE = "GPM IMERG: ~10 km resolution, ~3.5 month latency (final run); not real-time rainfall.";
export const EARTHDATA_BANNER =
  "Search works without credentials; downloads need an Earthdata login (see docs/earthdata-authentication.md).";

export function formatBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "unknown";
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[i]}`;
}

export const DATA_KIND_LABEL: Record<DataKind, string> = {
  metadata_only: "Metadata only",
  downloaded: "Downloaded",
  validated: "File passed integrity checks", // integrity only, NOT scientific validation
};
export const dataKindLabel = (k: DataKind) => DATA_KIND_LABEL[k];
export const dataKindVariant = (k: DataKind) =>
  (k === "validated" ? "ok" : k === "downloaded" ? "accent" : "neutral") as "ok" | "accent" | "neutral";

/** PROVISIONAL/BETA get the warn style so they read as lower maturity; unknown stays neutral. */
export const maturityVariant = (m: Maturity | null) =>
  (m === "VALIDATED" ? "ok" : m === null ? "neutral" : "demo") as "ok" | "demo" | "neutral";

/** Polling is only needed while a job can still change. */
export const hasActiveJobs = (jobs: Pick<DownloadJobRead, "status">[]) =>
  jobs.some((j) => j.status === "QUEUED" || j.status === "RUNNING");

export const progressPercent = (p: number) => Math.round(Math.min(1, Math.max(0, p)) * 100);

export type AoiResult = { ok: true; aoi: AOIInput } | { ok: false; error: string };

/** Exactly one of an area id or a pasted GeoJSON Polygon/MultiPolygon. */
export function buildAoi(areaId: string, geojsonText: string): AoiResult {
  const text = geojsonText.trim();
  if (areaId && text) return { ok: false, error: "Choose a monitored area OR paste GeoJSON, not both." };
  if (!areaId && !text) return { ok: false, error: "Choose a monitored area or paste a GeoJSON Polygon/MultiPolygon." };
  if (areaId) return { ok: true, aoi: { monitored_area_id: areaId } };
  let g: unknown;
  try {
    g = JSON.parse(text);
  } catch {
    return { ok: false, error: "GeoJSON is not valid JSON." };
  }
  const o = g as { type?: unknown; coordinates?: unknown } | null;
  if (!o || typeof o !== "object" || (o.type !== "Polygon" && o.type !== "MultiPolygon")) {
    return { ok: false, error: "Geometry type must be Polygon or MultiPolygon (a bare geometry, not a Feature)." };
  }
  if (!Array.isArray(o.coordinates) || o.coordinates.length === 0) {
    return { ok: false, error: "Geometry has no coordinates." };
  }
  return { ok: true, aoi: { geometry: o as Record<string, unknown> } };
}

/** Date inputs (YYYY-MM-DD) to ISO datetimes; error when start is after end. */
export function buildDateRange(
  start: string,
  end: string,
): { ok: true; start_date?: string; end_date?: string } | { ok: false; error: string } {
  if (start && end && start > end) return { ok: false, error: "Start date must not be after end date." };
  return {
    ok: true,
    start_date: start ? `${start}T00:00:00Z` : undefined,
    end_date: end ? `${end}T23:59:59Z` : undefined,
  };
}
