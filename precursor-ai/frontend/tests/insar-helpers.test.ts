import { afterEach, describe, expect, it, vi } from "vitest";
import {
  INSAR_DISCLAIMER, formatStat, hasActiveRuns, isSynthetic, isTerminal, originLabel, parseThreshold, statusLabel,
  statusTone,
} from "@/lib/insar-helpers";
import { createInsarRun, inspectInsarProduct, previewUrl, rasterUrl } from "@/services/insar";
import type { RunStatus } from "@/types/insar";

const BASE = "http://api.test/api/v1";
afterEach(() => vi.unstubAllGlobals());

describe("run status helpers", () => {
  it("knows terminal states", () => {
    for (const s of ["COMPLETED", "FAILED", "CANCELLED", "BLOCKED_MISSING_INPUT"] as RunStatus[]) expect(isTerminal(s)).toBe(true);
    for (const s of ["QUEUED", "INSPECTING", "DISPLACEMENT_CALCULATION"] as RunStatus[]) expect(isTerminal(s)).toBe(false);
  });
  it("polls only while something is active", () => {
    expect(hasActiveRuns([{ status: "COMPLETED" }, { status: "FAILED" }])).toBe(false);
    expect(hasActiveRuns([{ status: "COMPLETED" }, { status: "QUEUED" }])).toBe(true);
  });
  it("shows blocked input differently from failure", () => {
    expect(statusTone("BLOCKED_MISSING_INPUT")).toBe("warn");
    expect(statusTone("FAILED")).toBe("danger");
    expect(statusLabel("BLOCKED_MISSING_INPUT")).toMatch(/blocked/i);
    expect(statusLabel("DISPLACEMENT_CALCULATION")).toBe("Displacement calculation");
  });
});

describe("origin labelling never over-claims", () => {
  it("labels synthetic data loudly", () => {
    expect(originLabel("SYNTHETIC_FIXTURE")).toMatch(/SYNTHETIC TEST DATA/);
    expect(isSynthetic("SYNTHETIC_FIXTURE")).toBe(true);
    expect(isSynthetic("REAL_SATELLITE")).toBe(false);
  });
  it("never says validated for real or unverified data", () => {
    for (const o of ["REAL_SATELLITE", "LOCAL_UNVERIFIED"] as const) expect(originLabel(o)).toMatch(/not scientifically validated/);
  });
  it("states it is not a risk prediction", () => {
    expect(INSAR_DISCLAIMER).toMatch(/not a landslide risk/i);
  });
});

describe("parseThreshold", () => {
  it("blank means no masking", () => expect(parseThreshold("  ")).toBeNull());
  it("accepts 0..1", () => {
    expect(parseThreshold("0")).toBe(0);
    expect(parseThreshold("0.35")).toBe(0.35);
    expect(parseThreshold("1")).toBe(1);
  });
  it("rejects out of range and junk", () => {
    for (const bad of ["1.1", "-0.1", "abc", "NaN", "Infinity"]) expect(parseThreshold(bad)).toBeUndefined();
  });
});

describe("formatStat", () => {
  it("includes units and handles missing values", () => {
    expect(formatStat(-11.3461, "mm")).toBe("-11.346 mm");
    expect(formatStat(null, "mm")).toBe("n/a");
    expect(formatStat(undefined, "mm")).toBe("n/a");
    expect(formatStat(0, "mm")).toBe("0.000 mm");
    expect(formatStat(1e-6, "mm")).toMatch(/e-6 mm$/);
  });
});

describe("insar service", () => {
  function stub(body: unknown) {
    const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) });
    vi.stubGlobal("fetch", f);
    return f;
  }
  it("sends ids/sample names only, never a path field", async () => {
    const f = stub({ run: { id: "r" }, created: true });
    await createInsarRun({ sample_file: "s.h5" }, { coherence_threshold: 0.4, compute_velocity: true });
    const [url, init] = f.mock.calls[0];
    expect(String(url)).toMatch(/\/insar\/processing-runs$/);
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({ sample_file: "s.h5", config: { coherence_threshold: 0.4, compute_velocity: true } });
    expect(Object.keys(body)).not.toContain("path");
  });
  it("inspects by acquisition id", async () => {
    const f = stub({ product_kind: "GUNW" });
    await inspectInsarProduct({ acquisition_id: "abc" });
    expect(JSON.parse(String(f.mock.calls[0][1].body))).toEqual({ acquisition_id: "abc" });
  });
  it("builds id-only raster URLs", () => {
    expect(previewUrl("p1")).toMatch(/\/insar\/deformation-products\/p1\/preview$/);
    expect(rasterUrl("p1")).toMatch(/\/insar\/deformation-products\/p1\/raster$/);
    expect(BASE).toBeTruthy();
  });
});
