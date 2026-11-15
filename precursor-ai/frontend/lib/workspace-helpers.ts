export type AoiParse = { ok: true; geometry: Record<string, unknown>; name: string | null } | { ok: false; error: string };

/** Accepts a GeoJSON Polygon/MultiPolygon, a Feature, or a FeatureCollection with exactly one polygon feature. Coordinates are (lon, lat). */
export function parseAoiGeoJson(text: string): AoiParse {
  let obj: unknown;
  try {
    obj = JSON.parse(text);
  } catch {
    return { ok: false, error: "Not valid JSON" };
  }
  const o = obj as { type?: string; geometry?: unknown; features?: unknown[]; properties?: { name?: unknown } | null };
  let g: { type?: string; coordinates?: unknown } | undefined;
  let name: string | null = null;
  if (o?.type === "FeatureCollection") {
    if (!Array.isArray(o.features) || o.features.length !== 1) return { ok: false, error: "A FeatureCollection must hold exactly one feature" };
    const f = o.features[0] as { geometry?: typeof g; properties?: { name?: unknown } | null };
    g = f.geometry;
    name = typeof f.properties?.name === "string" ? f.properties.name : null;
  } else if (o?.type === "Feature") {
    g = o.geometry as typeof g;
    name = typeof o.properties?.name === "string" ? o.properties.name : null;
  } else g = o as typeof g;
  if (!g || (g.type !== "Polygon" && g.type !== "MultiPolygon")) return { ok: false, error: "Geometry must be a Polygon or MultiPolygon" };
  if (!Array.isArray(g.coordinates) || g.coordinates.length === 0) return { ok: false, error: "Geometry has no coordinates" };
  const bad = flatten(g.coordinates).some(([x, y]) => !Number.isFinite(x) || !Number.isFinite(y) || Math.abs(x) > 180 || Math.abs(y) > 90);
  if (bad) return { ok: false, error: "Coordinates must be finite (lon, lat) in EPSG:4326 (|lon| <= 180, |lat| <= 90)" };
  return { ok: true, geometry: g as Record<string, unknown>, name };
}

function flatten(c: unknown): [number, number][] {
  if (Array.isArray(c) && c.length >= 2 && typeof c[0] === "number") return [[c[0] as number, c[1] as number]];
  return Array.isArray(c) ? c.flatMap(flatten) : [];
}

/** Value of a numeric series at the day index (clamped); null if the series is empty. */
export const clampIndex = (i: number, n: number) => (n <= 0 ? 0 : Math.min(n - 1, Math.max(0, Math.trunc(i))));
