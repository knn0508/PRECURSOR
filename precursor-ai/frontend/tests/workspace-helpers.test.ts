import { describe, expect, it } from "vitest";
import { clampIndex, parseAoiGeoJson } from "@/lib/workspace-helpers";
import { isSyntheticOrMock, sourceKindForLayer, sourceKindForSeries } from "@/lib/source-badges";

const POLY = { type: "Polygon", coordinates: [[[116, 5], [116.2, 5], [116.2, 5.2], [116, 5.2], [116, 5]]] };

describe("AOI upload parsing", () => {
  it("accepts Polygon, Feature and a one-feature collection (any region)", () => {
    expect(parseAoiGeoJson(JSON.stringify(POLY))).toMatchObject({ ok: true });
    const f = parseAoiGeoJson(JSON.stringify({ type: "Feature", properties: { name: "Sabah" }, geometry: POLY }));
    expect(f).toMatchObject({ ok: true, name: "Sabah" });
    expect(parseAoiGeoJson(JSON.stringify({ type: "FeatureCollection", features: [{ type: "Feature", properties: null, geometry: POLY }] }))).toMatchObject({ ok: true });
    expect(parseAoiGeoJson(JSON.stringify({ type: "MultiPolygon", coordinates: [POLY.coordinates] }))).toMatchObject({ ok: true });
  });
  it("rejects bad input with a reason", () => {
    expect(parseAoiGeoJson("nope")).toEqual({ ok: false, error: "Not valid JSON" });
    expect(parseAoiGeoJson(JSON.stringify({ type: "Point", coordinates: [1, 2] }))).toMatchObject({ ok: false });
    expect(parseAoiGeoJson(JSON.stringify({ type: "FeatureCollection", features: [] }))).toMatchObject({ ok: false });
    expect(parseAoiGeoJson(JSON.stringify({ type: "Polygon", coordinates: [] }))).toMatchObject({ ok: false });
    const out = parseAoiGeoJson(JSON.stringify({ type: "Polygon", coordinates: [[[500, 5], [1, 5], [1, 6], [500, 5]]] }));
    expect(out).toMatchObject({ ok: false });
    expect(parseAoiGeoJson(JSON.stringify({ type: "Polygon", coordinates: [[[1, 95], [1, 5], [2, 6], [1, 95]]] }))).toMatchObject({ ok: false });
  });
  it("clamps slider indices", () => {
    expect(clampIndex(-3, 14)).toBe(0);
    expect(clampIndex(99, 14)).toBe(13);
    expect(clampIndex(2.7, 14)).toBe(2);
    expect(clampIndex(5, 0)).toBe(0);
  });
});

describe("source kinds", () => {
  it("synthetic always wins; unverified local data is never called satellite", () => {
    expect(sourceKindForLayer({ data_origin: "SYNTHETIC_FIXTURE", measurement_kind: "EXISTING_PROCESSED_PRODUCT" })).toBe("SYNTHETIC_DEMO");
    expect(sourceKindForLayer({ data_origin: "LOCAL_UNVERIFIED" })).toBe("REAL_DERIVED");
    expect(sourceKindForLayer({ data_origin: "REAL_SATELLITE", measurement_kind: "NEWLY_DERIVED" })).toBe("REAL_DERIVED");
    expect(sourceKindForLayer({ data_origin: "REAL_SATELLITE", measurement_kind: "RAW_OBSERVATION" })).toBe("REAL_SATELLITE");
    expect(sourceKindForLayer({})).toBe("PLACEHOLDER");
  });
  it("no helper ever yields MODEL_PREDICTION for data layers or series", () => {
    for (const o of ["SYNTHETIC_FIXTURE", "LOCAL_UNVERIFIED", "REAL_SATELLITE", undefined]) expect(sourceKindForLayer({ data_origin: o })).not.toBe("MODEL_PREDICTION");
    expect(sourceKindForSeries(true)).toBe("SYNTHETIC_DEMO");
    expect(sourceKindForSeries(false)).toBe("STATISTICAL");
    expect(isSyntheticOrMock("PLACEHOLDER") && isSyntheticOrMock("SYNTHETIC_DEMO") && !isSyntheticOrMock("STATISTICAL")).toBe(true);
  });
});
