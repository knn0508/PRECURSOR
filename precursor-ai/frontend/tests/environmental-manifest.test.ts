import { describe, expect, it } from "vitest";
import {
  buildProcessConfig, coveragePct, formatResolution, layerDisplayName, layerKind, manifestCounts, shortHash,
  validateGridCrs, validateGridResolution,
} from "@/lib/environmental-helpers";
import type { ManifestEntry } from "@/types/environmental";

const e = (o: Partial<ManifestEntry>) => o as ManifestEntry;

describe("process form helpers", () => {
  it("validates grid CRS", () => {
    for (const ok of ["", "EPSG:32650", "EPSG:4326"]) expect(validateGridCrs(ok)).toBeNull();
    for (const bad of ["32650", "epsg:32650", "EPSG:12", "EPSG:1234567"]) expect(validateGridCrs(bad)).not.toBeNull();
  });
  it("validates grid resolution", () => {
    for (const ok of ["", "30", "12.5"]) expect(validateGridResolution(ok)).toBeNull();
    for (const bad of ["0", "-5", "abc", "20000"]) expect(validateGridResolution(bad)).not.toBeNull();
  });
  it("sends only set fields", () => {
    expect(buildProcessConfig({ start: "", end: "", gridCrs: "", gridRes: "", rainfall: "daily" })).toEqual({});
  });
});

describe("layer kinds", () => {
  it("classifies raster/series/vector", () => {
    expect(layerKind("SMAP_SOIL_MOISTURE")).toBe("series");
    expect(layerKind("RAINFALL")).toBe("series");
    expect(layerKind("SEISMIC")).toBe("vector");
    for (const t of ["LITHOLOGY", "NDVI", "DISTANCE_RIVER", "SOIL"]) expect(layerKind(t)).toBe("raster");
  });
  it("names SOIL layers by dataset", () => {
    expect(layerDisplayName({ layer_type: "SOIL", dataset_name: "clay 0-5cm" })).toBe("Soil: clay 0-5cm");
    expect(layerDisplayName({ layer_type: "NDVI", dataset_name: "x" })).toBe("Ndvi");
  });
});

describe("manifest formatting", () => {
  it("counts kinds, temporal and synthetic", () => {
    expect(manifestCounts([
      e({ kind: "raster", temporal_kind: "static", synthetic: true }),
      e({ kind: "series", temporal_kind: "dynamic", synthetic: false }),
      e({ kind: "vector", temporal_kind: "static", synthetic: false }),
    ])).toEqual({ raster: 1, series: 1, vector: 1, static: 2, dynamic: 1, synthetic: 1 });
  });
  it("shows n/a for missing, never 0", () => {
    expect(coveragePct(null)).toBe("n/a");
    expect(coveragePct(undefined)).toBe("n/a");
    expect(coveragePct(0)).toBe("0.0%");
    expect(formatResolution(null)).toBe("n/a");
    expect(formatResolution({ x: 30, y: 30, unit: "m" })).toBe("30 m");
    expect(formatResolution({ x: 0.00027777777777777778, y: 0.00027777777777777778, unit: "degree" })).toBe("0.00027778 degree");
    expect(formatResolution({ x: 0.1, y: 0.09999999999999964, unit: "degree" })).toBe("0.1 degree"); // float noise is not a different resolution
    expect(shortHash(null)).toBe("n/a");
    expect(shortHash("abcdef0123456789")).toBe("abcdef0123");
  });
});
