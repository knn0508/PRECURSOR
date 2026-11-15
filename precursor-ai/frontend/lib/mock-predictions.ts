// MOCK prediction fixtures (ADR-0008, Phase 9). The ONLY place mock values are made. Delete this file and the flag to remove mock mode.
//
// Rules: values come from a fixed-seed generator and take NO real input (no area, no layer, no API response): they cannot be derived from
// real data by construction. Everything is labelled MOCK; nothing here can be exported; palette is neutral (a grey-violet ramp).

export const MOCK_BANNER_TEXT = "MOCK DATA: NOT A PREDICTION";
export const MOCK_BADGE_TEXT = "MOCK";
export const MOCK_SEED = 20261115;

/** mulberry32: small deterministic PRNG. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export interface MockGrid { readonly mock: true; rows: number; cols: number; values: number[] }
export interface MockSeries { readonly mock: true; days: number[]; values: number[] }
export interface MockContribution { readonly mock: true; feature: string; contribution: number }

/** Smooth value-noise grid in [0, 1] (bilinear blend of a coarse seeded lattice). Depends only on (seed, rows, cols). */
export function mockSusceptibilityGrid(seed: number, rows = 20, cols = 20): MockGrid {
  const rnd = mulberry32(seed);
  const lat = Array.from({ length: 5 * 5 }, () => rnd());
  const at = (i: number, j: number) => lat[Math.min(i, 4) * 5 + Math.min(j, 4)];
  const values: number[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const y = (r / Math.max(rows - 1, 1)) * 4, x = (c / Math.max(cols - 1, 1)) * 4;
      const i = Math.floor(y), j = Math.floor(x), fy = y - i, fx = x - j;
      const v = at(i, j) * (1 - fx) * (1 - fy) + at(i, j + 1) * fx * (1 - fy) + at(i + 1, j) * (1 - fx) * fy + at(i + 1, j + 1) * fx * fy;
      values.push(Math.round(v * 1000) / 1000);
    }
  }
  return { mock: true, rows, cols, values };
}

/** Trigger-view mock: a seeded random walk in [0, 1] over `days` steps for a given cursor day (the day changes the seed only). */
export function mockTriggerSeries(seed: number, days = 14): MockSeries {
  const rnd = mulberry32(seed ^ 0x9e3779b9);
  let v = 0.3 + 0.4 * rnd();
  const values: number[] = [];
  for (let d = 0; d < days; d++) {
    v = Math.min(1, Math.max(0, v + (rnd() - 0.5) * 0.25));
    values.push(Math.round(v * 1000) / 1000);
  }
  return { mock: true, days: Array.from({ length: days }, (_, i) => i + 1), values };
}

/** Mock "explanation": placeholder feature names that match no real feature, so it cannot read as a real attribution. */
export function mockContributions(seed: number): MockContribution[] {
  const rnd = mulberry32(seed ^ 0x85ebca6b);
  return Array.from({ length: 5 }, (_, i) => ({ mock: true as const, feature: `mock_feature_${i + 1}`, contribution: Math.round((rnd() - 0.5) * 200) / 100 }));
}

/** Neutral sequential ramp (dark to light grey). Deliberately has no red/amber/green semantics. */
export function neutralRamp(v: number): string {
  const t = Math.min(1, Math.max(0, v));
  const a = [38, 42, 50], b = [226, 230, 238]; // near-neutral grey, dark -> light (channels within ~12 of each other)
  const c = a.map((x, i) => Math.round(x + (b[i] - x) * t));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}
