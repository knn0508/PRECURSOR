import { isSynthetic } from "@/lib/insar-helpers";
import type { DataOrigin, EventFeature, LayerRead, LegendClass, ManifestEntry, ProcessConfig, RainfallPoint } from "@/types/environmental";

export { isSynthetic };

export const ENV_DISCLAIMER =
  "Environmental measurements and summaries of source data. Not a landslide risk map, score or prediction.";
export const INSAR_LAYER_NOTE = "Deformation map, not a risk map.";
export const IMERG_NOTE =
  "IMERG Final Run has roughly 3.5 months of latency and is not real-time. Values are accumulated precipitation (mm), not a rate.";
export const AOI_COLOR = "#38bdf8";

/** Badge text for a data origin. Synthetic is loud; real is never called validated. */
export function originBadge(o: DataOrigin | null | undefined): { text: string; tone: "warn" | "neutral" } {
  if (o === "SYNTHETIC_FIXTURE") return { text: "SYNTHETIC TEST DATA", tone: "warn" };
  if (o === "LOCAL_UNVERIFIED") return { text: "UNVERIFIED", tone: "warn" };
  if (o === "REAL_SATELLITE") return { text: "Source data, not validated", tone: "neutral" };
  return { text: "Origin unknown", tone: "neutral" };
}

export const originNote = (o: DataOrigin | null | undefined): string =>
  o === "SYNTHETIC_FIXTURE"
    ? "SYNTHETIC TEST DATA: not a real measurement."
    : o === "LOCAL_UNVERIFIED"
      ? "UNVERIFIED: local data of unknown provenance, not a validated measurement."
      : o === "REAL_SATELLITE"
        ? "Derived from source data; not scientifically validated."
        : "Origin not determined.";

export const needsWarning = (o: DataOrigin | null | undefined) => o === "SYNTHETIC_FIXTURE" || o === "LOCAL_UNVERIFIED";

// ---- runs ----
const TERMINAL = ["COMPLETED", "PARTIAL", "FAILED", "CANCELLED"];
export const isTerminalRun = (s: string) => TERMINAL.includes(s);
/** Poll only while a run exists and is non-terminal. */
export const shouldPoll = (s: string | null | undefined) => !!s && !isTerminalRun(s);

export const runStatusTone = (s: string): "ok" | "warn" | "danger" | "accent" =>
  s === "COMPLETED" ? "ok" : s === "PARTIAL" || s === "CANCELLED" ? "warn" : s === "FAILED" ? "danger" : "accent";

export const runStatusLabel = (s: string) =>
  s === "PARTIAL" ? "Partial (some stages had no input)" : s.replaceAll("_", " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());

/** NOT_AVAILABLE is "no input available", never a failure or zero. */
export function stageLabel(s: string): { text: string; tone: "ok" | "warn" | "danger" | "accent" | "neutral" } {
  switch (s) {
    case "DONE": return { text: "Done", tone: "ok" };
    case "PARTIAL": return { text: "Partial", tone: "warn" };
    case "NOT_AVAILABLE": return { text: "No input available", tone: "neutral" };
    case "SKIPPED": return { text: "Skipped", tone: "neutral" };
    case "FAILED": return { text: "Failed", tone: "danger" };
    case "RUNNING": return { text: "Running", tone: "accent" };
    default: return { text: s, tone: "neutral" };
  }
}

// ---- dates ----
const DAY_MS = 86_400_000;
const ISO = /^\d{4}-\d{2}-\d{2}$/;
/** Returns an error message, or null when valid. Mirrors the backend validators (both-or-neither, end>=start, <=3660 days). */
export function validateDateRange(start: string, end: string, opts: { required?: boolean } = {}): string | null {
  if (!start && !end) return opts.required ? "Start and end dates are required." : null;
  if (!start || !end) return "Give both start and end dates, or neither.";
  if (!ISO.test(start) || !ISO.test(end)) return "Dates must be YYYY-MM-DD.";
  const s = Date.parse(start), e = Date.parse(end);
  if (Number.isNaN(s) || Number.isNaN(e)) return "Invalid date.";
  if (e < s) return "End date must not be before start date.";
  if ((e - s) / DAY_MS > 3660) return "Date range is longer than 10 years.";
  return null;
}

/** "" -> null (no filter); valid 0..10 -> number; otherwise undefined. */
export function parseMagnitude(raw: string): number | null | undefined {
  const t = raw.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 && n <= 10 ? n : undefined;
}

// ---- series ----
export interface ChartPoint { date: string; value: number | null; missing: boolean }
/** Null stays null (a gap). A point without an observation is missing regardless of its value. */
export function toSeries(points: RainfallPoint[]): ChartPoint[] {
  return points.map((p) => {
    const ok = p.observed && p.precipitation_mm !== null && p.precipitation_mm !== undefined;
    return { date: p.date, value: ok ? p.precipitation_mm : null, missing: !ok };
  });
}
export const countSeries = (s: ChartPoint[]) => {
  const missing = s.filter((p) => p.missing).length;
  return { observed: s.length - missing, missing };
};

/** Merge rolling windows into one row per date for a multi-line chart; absent window values stay null. */
export function mergeRolling(rolling: Record<string, RainfallPoint[]>): { keys: string[]; rows: Record<string, string | number | null>[] } {
  const keys = Object.keys(rolling).sort((a, b) => parseInt(a) - parseInt(b));
  const byDate = new Map<string, Record<string, string | number | null>>();
  for (const k of keys) {
    for (const p of toSeries(rolling[k])) {
      const row = byDate.get(p.date) ?? { date: p.date };
      row[k] = p.value;
      byDate.set(p.date, row);
    }
  }
  const rows = [...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)));
  for (const r of rows) for (const k of keys) if (!(k in r)) r[k] = null;
  return { keys, rows };
}

// ---- formatting ----
export function formatValue(v: unknown, unit?: string | null, digits = 2): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "n/a";
  const s = Math.abs(v) >= 1e5 ? v.toExponential(2) : v.toFixed(digits);
  return unit ? `${s} ${unit}` : s;
}
export const formatPercent = (v: number | null | undefined) => (typeof v === "number" ? `${v.toFixed(1)}%` : "n/a");

// ---- legend ----
export const GRADIENT_STOPS = ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"];
export function legendGradient(vmin: number | null, vmax: number | null, units: string | null, colors?: string[]) {
  if (vmin === null || vmax === null) return null;
  // Use the server's ramp so the legend always matches the preview PNG; fall back only if it is absent.
  const stops = colors && colors.length >= 2 ? colors : GRADIENT_STOPS;
  return {
    css: `linear-gradient(to right, ${stops.join(", ")})`,
    minLabel: formatValue(vmin, units),
    maxLabel: formatValue(vmax, units),
  };
}
export const legendClasses = (c: LegendClass[]) =>
  [...c].sort((a, b) => a.id - b.id).map((x) => ({ key: x.id, name: x.name, color: /^#[0-9a-fA-F]{3,8}$/.test(x.color) ? x.color : "#888888" }));

// ---- layers / map ----
export const isInsarLayer = (t: string) => t.startsWith("INSAR");
export const isVectorLayer = (t: string) => t === "HISTORICAL_LANDSLIDES" || t === "SEISMIC";
export const isSeriesLayer = (t: string) => t === "RAINFALL" || t === "SMAP_SOIL_MOISTURE";
export type LayerKind = "raster" | "series" | "vector";
export const layerKind = (t: string): LayerKind => (isVectorLayer(t) ? "vector" : isSeriesLayer(t) ? "series" : "raster");
/** SOIL can have several layers (property/depth): name each by its dataset. */
export const layerDisplayName = (l: Pick<LayerRead, "layer_type" | "dataset_name">) =>
  l.layer_type === "SOIL" && l.dataset_name ? `${layerTypeLabel(l.layer_type)}: ${l.dataset_name}` : layerTypeLabel(l.layer_type);
export const layerTypeLabel = (t: string) => t.replaceAll("_", " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());
/** A raster is drawable only when processed data with a raster and a footprint exists; otherwise show "no data", never zeros. */
export const isDrawableRaster = (l: LayerRead) =>
  l.has_raster && (l.status === "PROCESSED" || l.status === "PARTIALLY_PROCESSED") && footprintCorners(l.footprint) !== null;

type LonLat = [number, number];
function walk(c: unknown, out: LonLat[]) {
  if (Array.isArray(c) && typeof c[0] === "number" && typeof c[1] === "number") out.push([c[0], c[1]]);
  else if (Array.isArray(c)) c.forEach((x) => walk(x, out));
}
export function bboxOf(geom: unknown): [number, number, number, number] | null {
  if (!geom || typeof geom !== "object") return null;
  const pts: LonLat[] = [];
  walk((geom as { coordinates?: unknown }).coordinates, pts);
  const ok = pts.filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y) && Math.abs(x) <= 180 && Math.abs(y) <= 90);
  if (ok.length === 0 || ok.length !== pts.length) return null;
  const xs = ok.map((p) => p[0]), ys = ok.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
/** MapLibre image-source corners (EPSG:4326): top-left, top-right, bottom-right, bottom-left. */
export function footprintCorners(footprint: unknown): [LonLat, LonLat, LonLat, LonLat] | null {
  const b = bboxOf(footprint);
  if (!b || b[0] === b[2] || b[1] === b[3]) return null;
  const [w, s, e, n] = b;
  return [[w, n], [e, n], [e, s], [w, s]];
}

export const eventFeatures = (g: { features?: EventFeature[] } | null | undefined): EventFeature[] =>
  Array.isArray(g?.features) ? g.features : [];

// ---- generic summary-value helpers (backend `values` / `report` are free-form dicts) ----
export interface Bin { label: string; count: number }
/** Accepts [n,...], [{label|bin|range|name, count|value}], or {label: n}. Returns null when it is not histogram-shaped. */
export function toBins(v: unknown): Bin[] | null {
  const num = (x: unknown) => (typeof x === "number" && Number.isFinite(x) ? x : null);
  if (Array.isArray(v)) {
    if (v.length === 0) return null;
    if (v.every((x) => num(x) !== null)) return (v as number[]).map((c, i) => ({ label: String(i), count: c }));
    const out: Bin[] = [];
    for (const x of v) {
      if (!x || typeof x !== "object") return null;
      const o = x as Record<string, unknown>;
      const c = num(o.count ?? o.value ?? o.pixels);
      const l = o.label ?? o.bin ?? o.range ?? o.name ?? o.sector;
      if (c === null || l === undefined) return null;
      out.push({ label: String(l), count: c });
    }
    return out;
  }
  if (v && typeof v === "object") {
    const e = Object.entries(v as Record<string, unknown>);
    if (e.length === 0 || !e.every(([, x]) => num(x) !== null)) return null;
    return e.map(([k, x]) => ({ label: k, count: x as number }));
  }
  return null;
}

/** Split a free-form `values` dict into scalar stats (one nested level flattened as "a.b") and histogram-shaped series. */
export function splitValues(values: Record<string, unknown>, units: Record<string, string> = {}) {
  const stats: { key: string; value: number | string | boolean | null; unit: string | null }[] = [];
  const charts: { key: string; bins: Bin[] }[] = [];
  const unitOf = (k: string) => units[k] ?? units[k.split(".")[0]] ?? null;
  for (const [k, v] of Object.entries(values)) {
    const bins = Array.isArray(v) || (v && typeof v === "object" && Object.values(v as object).every((x) => typeof x === "number")) ? toBins(v) : null;
    if (bins && (Array.isArray(v) || /hist|distribution|sector|bins|classes/i.test(k))) charts.push({ key: k, bins });
    else if (v && typeof v === "object" && !Array.isArray(v)) {
      for (const [k2, v2] of Object.entries(v as Record<string, unknown>)) {
        if (v2 === null || ["number", "string", "boolean"].includes(typeof v2)) stats.push({ key: `${k}.${k2}`, value: v2 as number | string | boolean | null, unit: unitOf(`${k}.${k2}`) });
      }
    } else if (v === null || ["number", "string", "boolean"].includes(typeof v)) stats.push({ key: k, value: v as number | string | boolean | null, unit: unitOf(k) });
  }
  return { stats, charts };
}

// ---- process form (grid / rainfall) ----
export const validateGridCrs = (raw: string): string | null =>
  raw.trim() === "" || /^EPSG:\d{4,6}$/.test(raw.trim()) ? null : "Grid CRS must look like EPSG:32650, or be blank.";
export function validateGridResolution(raw: string): string | null {
  const t = raw.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) && n > 0 && n <= 10000 ? null : "Grid resolution must be a number of metres above 0 (max 10000), or blank.";
}
/** Only set fields are sent; never a path. Callers must validate first. */
export function buildProcessConfig(f: { start: string; end: string; gridCrs: string; gridRes: string; rainfall: string }): ProcessConfig {
  const cfg: ProcessConfig = {};
  if (f.start && f.end) { cfg.start_date = f.start; cfg.end_date = f.end; }
  if (f.gridCrs.trim()) cfg.grid_crs = f.gridCrs.trim();
  if (f.gridRes.trim()) cfg.grid_resolution_m = Number(f.gridRes);
  if (f.rainfall === "half_hourly") cfg.rainfall_resolution = "half_hourly";
  return cfg;
}

// ---- manifest ----
export function manifestCounts(entries: ManifestEntry[]) {
  const c = { raster: 0, series: 0, vector: 0, static: 0, dynamic: 0, synthetic: 0 };
  for (const e of entries) {
    if (e.kind === "raster" || e.kind === "series" || e.kind === "vector") c[e.kind]++;
    if (e.temporal_kind === "static") c.static++;
    else if (e.temporal_kind === "dynamic") c.dynamic++;
    if (e.synthetic) c.synthetic++;
  }
  return c;
}
export const shortHash = (h: string | null | undefined) => (h ? h.slice(0, 10) : "n/a");
/** Missing is "n/a", never 0%. */
export const coveragePct = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? `${v.toFixed(1)}%` : "n/a");
export function formatResolution(r: Record<string, unknown> | null | undefined): string {
  if (!r) return "n/a";
  const { x, y, unit } = r as { x?: unknown; y?: unknown; unit?: unknown };
  if (typeof x !== "number") return "n/a";
  const u = typeof unit === "string" ? ` ${unit}` : "";
  const f = (n: number) => String(Number(n.toPrecision(5))); // 0.00027777777777777778 -> 0.00027778
  return typeof y === "number" && f(y) !== f(x) ? `${f(x)} x ${f(y)}${u}` : `${f(x)}${u}`;
}
export const manifestFilename = (areaId: string) => `manifest-${areaId.slice(0, 8)}.json`;
