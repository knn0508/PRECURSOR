import { describe, expect, it } from "vitest";
import {
  countSeries, footprintCorners, formatValue, isDrawableRaster, isTerminalRun, legendClasses, legendGradient,
  mergeRolling, originBadge, originNote, parseMagnitude, shouldPoll, stageLabel, toBins, toSeries, validateDateRange,
} from "@/lib/environmental-helpers";
import type { LayerRead } from "@/types/environmental";

describe("origin labels", () => {
  it("flags synthetic and unverified loudly, never calls real validated", () => {
    expect(originBadge("SYNTHETIC_FIXTURE")).toEqual({ text: "SYNTHETIC TEST DATA", tone: "warn" });
    expect(originBadge("LOCAL_UNVERIFIED").text).toBe("UNVERIFIED");
    expect(originBadge("REAL_SATELLITE").text).not.toMatch(/^validated/i);
    expect(originNote("REAL_SATELLITE")).toMatch(/not scientifically validated/);
    expect(originNote("SYNTHETIC_FIXTURE")).toMatch(/not a real measurement/);
  });
});

describe("runs", () => {
  it("detects terminal runs and polls only while non-terminal", () => {
    for (const s of ["COMPLETED", "PARTIAL", "FAILED", "CANCELLED"]) expect(isTerminalRun(s)).toBe(true);
    expect(shouldPoll("RUNNING")).toBe(true);
    expect(shouldPoll("QUEUED")).toBe(true);
    expect(shouldPoll("PARTIAL")).toBe(false);
    expect(shouldPoll(undefined)).toBe(false);
  });
  it("shows NOT_AVAILABLE as no input, not failure", () => {
    expect(stageLabel("NOT_AVAILABLE")).toEqual({ text: "No input available", tone: "neutral" });
    expect(stageLabel("PARTIAL").tone).toBe("warn");
    expect(stageLabel("FAILED").tone).toBe("danger");
  });
});

describe("validateDateRange", () => {
  it("accepts empty when optional, rejects when required", () => {
    expect(validateDateRange("", "")).toBeNull();
    expect(validateDateRange("", "", { required: true })).toMatch(/required/);
  });
  it("requires both or neither", () => expect(validateDateRange("2024-01-01", "")).toMatch(/both/));
  it("rejects end before start and >10 years", () => {
    expect(validateDateRange("2024-02-01", "2024-01-01")).toMatch(/before/);
    expect(validateDateRange("2010-01-01", "2024-01-01")).toMatch(/10 years/);
    expect(validateDateRange("2024-01-01", "2024-01-01")).toBeNull();
  });
  it("rejects malformed dates", () => expect(validateDateRange("01/01/2024", "2024-01-02")).toMatch(/YYYY/));
});

describe("parseMagnitude", () => {
  it("blank, valid, invalid", () => {
    expect(parseMagnitude("")).toBeNull();
    expect(parseMagnitude("4.5")).toBe(4.5);
    for (const b of ["11", "-1", "x"]) expect(parseMagnitude(b)).toBeUndefined();
  });
});

describe("rainfall series", () => {
  const pts = [
    { date: "2024-01-01", precipitation_mm: 0, observed: true },
    { date: "2024-01-02", precipitation_mm: null, observed: false },
    { date: "2024-01-03", precipitation_mm: 5, observed: true },
  ];
  it("keeps null as null and a real zero as zero", () => {
    const s = toSeries(pts);
    expect(s.map((p) => p.value)).toEqual([0, null, 5]);
    expect(countSeries(s)).toEqual({ observed: 2, missing: 1 });
  });
  it("merges rolling windows with gaps", () => {
    const m = mergeRolling({ "7d": pts, "3d": [pts[2]] });
    expect(m.keys).toEqual(["3d", "7d"]);
    expect(m.rows[0]["3d"]).toBeNull();
    expect(m.rows[1]["7d"]).toBeNull();
    expect(m.rows[2]["3d"]).toBe(5);
  });
});

describe("legend", () => {
  it("builds gradient with units, none when range unknown", () => {
    expect(legendGradient(0, 45, "degrees")?.maxLabel).toBe("45.00 degrees");
    expect(legendGradient(null, 1, "m")).toBeNull();
    expect(legendGradient(0, 1, "m", ["#000000", "#ffffff"])?.css).toBe("linear-gradient(to right, #000000, #ffffff)");
    expect(legendGradient(0, 1, "m", [])?.css).toContain("#440154"); // fallback only when the server sent no ramp
  });
  it("sorts classes and sanitises colours", () => {
    const c = legendClasses([{ id: 2, name: "b", color: "#fff" }, { id: 1, name: "a", color: "javascript:x" }]);
    expect(c.map((x) => x.key)).toEqual([1, 2]);
    expect(c[0].color).toBe("#888888");
  });
});

describe("footprintCorners", () => {
  const poly = { type: "Polygon", coordinates: [[[100, 5], [101, 5], [101, 6], [100, 6], [100, 5]]] };
  it("returns TL,TR,BR,BL from the bbox", () => {
    expect(footprintCorners(poly)).toEqual([[100, 6], [101, 6], [101, 5], [100, 5]]);
  });
  it("rejects null, out-of-range and degenerate footprints", () => {
    expect(footprintCorners(null)).toBeNull();
    expect(footprintCorners({ coordinates: [[[200, 5], [201, 6]]] })).toBeNull();
    expect(footprintCorners({ coordinates: [[[1, 1], [1, 1]]] })).toBeNull();
  });
  it("only draws processed rasters", () => {
    const base = { has_raster: true, status: "PROCESSED", footprint: poly } as unknown as LayerRead;
    expect(isDrawableRaster(base)).toBe(true);
    expect(isDrawableRaster({ ...base, status: "NOT_AVAILABLE" })).toBe(false);
    expect(isDrawableRaster({ ...base, has_raster: false })).toBe(false);
  });
});

describe("formatValue / toBins", () => {
  it("formats with units and n/a for missing (never 0)", () => {
    expect(formatValue(12.345, "m")).toBe("12.35 m");
    expect(formatValue(null, "m")).toBe("n/a");
  });
  it("normalises histogram shapes", () => {
    expect(toBins([1, 2])).toEqual([{ label: "0", count: 1 }, { label: "1", count: 2 }]);
    expect(toBins({ N: 3 })).toEqual([{ label: "N", count: 3 }]);
    expect(toBins([{ bin: "0-5", count: 4 }])).toEqual([{ label: "0-5", count: 4 }]);
    expect(toBins("x")).toBeNull();
    expect(toBins([])).toBeNull();
  });
});
