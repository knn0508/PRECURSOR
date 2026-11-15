import { afterEach, describe, expect, it, vi } from "vitest";
import { cellAt, colorLimit, divergingColor, fmtMm, skillPct, smoothGrid, sortByMae } from "@/lib/displacement-helpers";
import { displacementImageUrl, getDisplacementStatus } from "@/services/displacement";
import type { BenchmarkRow } from "@/types/displacement";

afterEach(() => vi.unstubAllGlobals());

describe("displacement helpers", () => {
  it("makes missing estimates transparent and signs distinct", () => {
    expect(divergingColor(null, 5)[3]).toBe(0);
    const [r1, , b1] = divergingColor(5, 5);
    const [r2, , b2] = divergingColor(-5, 5);
    expect(r1).toBeGreaterThan(b1);
    expect(b2).toBeGreaterThan(r2);
  });
  it("colour limit ignores nulls and is at least 1 mm", () => {
    expect(colorLimit([[null, 0.1], [0.2, null]])).toBe(1);
    expect(colorLimit([[null, null]])).toBe(1);
    expect(colorLimit([[10, -10, null]])).toBe(10);
  });
  it("maps pointer to grid cell and rejects outside", () => {
    expect(cellAt(0, 0, 100, 50, 10, 5)).toEqual([0, 0]);
    expect(cellAt(99, 49, 100, 50, 10, 5)).toEqual([4, 9]);
    expect(cellAt(100, 10, 100, 50, 10, 5)).toBeNull();
  });
  it("formats mm and skill", () => {
    expect(fmtMm(1.234)).toBe("+1.23 mm");
    expect(fmtMm(null)).toBe("n/a");
    expect(skillPct(2.45, 2.79)).toBeCloseTo(12.2, 1);
  });
  it("smooths finite neighbours only and keeps no-estimate cells null", () => {
    const g = [[0, 3, null], [3, 0, 3]];
    const s = smoothGrid(g);
    expect(s[0][2]).toBeNull();
    expect(s[0][0]).toBeCloseTo((0 + 3 + 3 + 0) / 4);
  });
  it("sorts by MAE and drops rows without one", () => {
    const rows = [{ model: "a", MAE_mm: 3 }, { model: "b", MAE_mm: null }, { model: "c", MAE_mm: 2 }] as BenchmarkRow[];
    expect(sortByMae(rows).map((r) => r.model)).toEqual(["c", "a"]);
  });
});

describe("displacement service", () => {
  it("builds image urls and requests status", async () => {
    expect(displacementImageUrl("forecast_map")).toMatch(/\/displacement-forecast\/images\/forecast_map$/);
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ available: true }) });
    vi.stubGlobal("fetch", f);
    await getDisplacementStatus();
    expect(String(f.mock.calls[0][0])).toMatch(/\/displacement-forecast\/status$/);
  });
});
