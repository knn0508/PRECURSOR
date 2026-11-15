import type { BenchmarkRow } from "@/types/displacement";

export const DISPLACEMENT_DISCLAIMER =
  "Research demonstrator. Inferred 12-day line-of-sight (LOS) displacement increment from Sentinel-1 OPERA data at one site. Not an operational warning and not a landslide probability.";

/** Diverging colour for a signed mm value: blue = away from satellite, red = toward it; saturates at +/-limit. null = no estimate. */
export function divergingColor(v: number | null, limit: number): [number, number, number, number] {
  if (v === null || !Number.isFinite(v)) return [0, 0, 0, 0];
  const t = Math.max(-1, Math.min(1, v / limit));
  const a = Math.abs(t);
  const base = 245 - Math.round(a * 160);
  return t >= 0 ? [245, base, base, 235] : [base, base + 10 > 255 ? 255 : base + 10, 245, 235];
}

/** Symmetric colour limit: 98th percentile of |q50|, at least 1 mm. */
export function colorLimit(grid: (number | null)[][]): number {
  const a: number[] = [];
  for (const row of grid) for (const v of row) if (v !== null) a.push(Math.abs(v));
  if (!a.length) return 1;
  a.sort((x, y) => x - y);
  return Math.max(1, a[Math.min(a.length - 1, Math.floor(a.length * 0.98))]);
}

/** Cell under a pointer inside an image of size (w,h) drawn from a grid of (cols,rows); null if outside. */
export function cellAt(px: number, py: number, w: number, h: number, cols: number, rows: number): [number, number] | null {
  if (px < 0 || py < 0 || px >= w || py >= h) return null;
  return [Math.min(rows - 1, Math.floor((py / h) * rows)), Math.min(cols - 1, Math.floor((px / w) * cols))];
}

export function fmtMm(v: number | null | undefined, digits = 2): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "n/a" : `${v >= 0 ? "+" : ""}${v.toFixed(digits)} mm`;
}

/** Skill vs the best naive baseline, in percent; positive = better. Compares model MAE only (not an accuracy claim on landslide motion). */
export function skillPct(maeModel: number, maeNaive: number): number {
  return maeNaive > 0 ? (1 - maeModel / maeNaive) * 100 : 0;
}

/** Benchmark rows are numeric strings or numbers; normalise (CSV-derived JSON may carry null). */
export function sortByMae(rows: BenchmarkRow[]): BenchmarkRow[] {
  return [...rows].filter((r) => r.MAE_mm !== null).sort((a, b) => (a.MAE_mm as number) - (b.MAE_mm as number));
}

/** Render a forecast band to a PNG data URL (browser only). Null cells stay transparent. */
export function gridToDataUrl(grid: (number | null)[][], limit: number): string | null {
  if (typeof document === "undefined" || !grid.length) return null;
  const h = grid.length, w = grid[0].length;
  const cv = document.createElement("canvas");
  cv.width = w; cv.height = h;
  const ctx = cv.getContext("2d");
  if (!ctx) return null;
  const img = ctx.createImageData(w, h);
  for (let r = 0; r < h; r++) for (let c = 0; c < w; c++) img.data.set(divergingColor(grid[r][c], limit), (r * w + c) * 4);
  ctx.putImageData(img, 0, 0);
  return cv.toDataURL("image/png");
}

/** 3x3 mean over finite neighbours, for DISPLAY only (the per-pixel values are speckled by OPERA noise). Cells with no estimate stay null. */
export function smoothGrid(grid: (number | null)[][]): (number | null)[][] {
  const h = grid.length, w = grid[0]?.length ?? 0;
  return grid.map((row, r) => row.map((v, c) => {
    if (v === null) return null;
    let s = 0, n = 0;
    for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
      const x = grid[r + dr]?.[c + dc];
      if (r + dr >= 0 && r + dr < h && c + dc >= 0 && c + dc < w && x !== null && x !== undefined) { s += x; n++; }
    }
    return n ? s / n : null;
  }));
}
