import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getCoverage, getManifest, getRun, layerPreviewUrl, listRuns, refreshSeismic, startProcessing,
} from "@/services/environmental";

import { buildProcessConfig } from "@/lib/environmental-helpers";

afterEach(() => vi.unstubAllGlobals());

function stub() {
  const f = vi.fn(async () => new Response(JSON.stringify({ run: {} }), { status: 200 }));
  vi.stubGlobal("fetch", f);
  return f;
}
const call = (f: ReturnType<typeof stub>) => {
  const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit | undefined];
  return { url, init };
};

describe("environmental service", () => {
  it("GETs coverage and runs by id", async () => {
    const f = stub();
    await getCoverage("a1");
    expect(call(f).url).toMatch(/\/environmental\/areas\/a1\/coverage$/);
    const g = stub();
    await getRun("r1");
    expect(call(g).url).toMatch(/\/environmental\/processing-runs\/r1$/);
  });
  it("builds run list query, omitting empty params", async () => {
    const f = stub();
    await listRuns({ area_id: "a1", status: "" });
    expect(call(f).url).toMatch(/processing-runs\?area_id=a1$/);
  });
  it("POSTs process config as JSON with no path field", async () => {
    const f = stub();
    await startProcessing("a1", { start_date: "2024-01-01", end_date: "2024-02-01" });
    const { url, init } = call(f);
    expect(url).toMatch(/areas\/a1\/process$/);
    expect(init?.method).toBe("POST");
    const body = JSON.parse(init?.body as string);
    expect(body).toEqual({ start_date: "2024-01-01", end_date: "2024-02-01" });
    expect(Object.keys(body).join()).not.toMatch(/path|file/i);
  });
  it("POSTs seismic refresh body", async () => {
    const f = stub();
    await refreshSeismic("a1", { start_date: "2024-01-01", end_date: "2024-01-31", min_magnitude: 4 });
    const { url, init } = call(f);
    expect(url).toMatch(/areas\/a1\/seismic\/refresh$/);
    expect(JSON.parse(init?.body as string).min_magnitude).toBe(4);
  });
  it("preview URL uses the layer id only", () => {
    expect(layerPreviewUrl("L1")).toMatch(/\/environmental\/layers\/L1\/preview$/);
  });
  it("GETs the manifest by area id", async () => {
    const f = stub();
    await getManifest("a1");
    expect(call(f).url).toMatch(/\/environmental\/areas\/a1\/manifest$/);
  });
  it("POST body has new fields only when set, never a path", async () => {
    const f = stub();
    await startProcessing("a1", buildProcessConfig({ start: "", end: "", gridCrs: "EPSG:32650", gridRes: "30", rainfall: "half_hourly" }));
    const body = JSON.parse(call(f).init?.body as string);
    expect(body).toEqual({ grid_crs: "EPSG:32650", grid_resolution_m: 30, rainfall_resolution: "half_hourly" });
    expect(Object.keys(body).join()).not.toMatch(/path|file/i);
  });
});
