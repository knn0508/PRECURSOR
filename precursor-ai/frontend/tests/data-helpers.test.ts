import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiPost, buildQuery } from "@/lib/api-client";
import {
  buildAoi, buildDateRange, dataKindLabel, formatBytes, hasActiveJobs, maturityVariant, progressPercent,
} from "@/lib/data-helpers";
import {
  acquireEnvironmental, createDownloads, importLandslideEvents, listCollections, listDataAcquisitions,
  listDownloads, retryDownload, searchData,
} from "@/services/data";

const BASE = "http://api.test/api/v1";
afterEach(() => vi.unstubAllGlobals());
function mockFetch(status = 200, body: unknown = {}) {
  const f = vi.fn(async (_u: string, _i?: RequestInit) => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", f);
  return f;
}

describe("apiPost", () => {
  it("sends JSON body with POST", async () => {
    const f = mockFetch(202, { ok: 1 });
    expect(await apiPost("/x", { a: 1 }, { baseUrl: BASE })).toEqual({ ok: 1 });
    const [url, init] = f.mock.calls[0];
    expect(url).toBe(`${BASE}/x`);
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe('{"a":1}');
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });
  it("maps error envelope", async () => {
    mockFetch(422, { error: { code: "validation_error", message: "bad aoi" } });
    await expect(apiPost("/x", {}, { baseUrl: BASE })).rejects.toMatchObject({ status: 422, code: "validation_error", message: "bad aoi" });
  });
  it("times out", async () => {
    vi.stubGlobal("fetch", (_u: string, init?: RequestInit) =>
      new Promise((_r, rej) => init?.signal?.addEventListener("abort", () => rej(new DOMException("a", "AbortError")))));
    const e = await apiPost<never>("/x", {}, { baseUrl: BASE, timeoutMs: 20 }).catch((x: unknown) => x as ApiError);
    expect(e.code).toBe("timeout");
  });
});

describe("buildQuery", () => {
  it("omits undefined, null and empty values", () => {
    expect(buildQuery({ a: 1, b: undefined, c: "", d: null, e: false, f: "x y" })).toBe("?a=1&e=false&f=x+y");
    expect(buildQuery({ a: undefined })).toBe("");
  });
});

describe("helpers", () => {
  it("formatBytes", () => {
    expect(formatBytes(null)).toBe("unknown");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(1.4 * 1024 ** 3)).toBe("1.4 GB");
  });
  it("data kind label never claims scientific validation", () => {
    expect(dataKindLabel("metadata_only")).toBe("Metadata only");
    expect(dataKindLabel("downloaded")).toBe("Downloaded");
    expect(dataKindLabel("validated")).toBe("File passed integrity checks");
  });
  it("maturity variant flags lower maturity", () => {
    expect(maturityVariant("VALIDATED")).toBe("ok");
    expect(maturityVariant("PROVISIONAL")).toBe("demo");
    expect(maturityVariant("BETA")).toBe("demo");
    expect(maturityVariant(null)).toBe("neutral");
  });
  it("hasActiveJobs", () => {
    expect(hasActiveJobs([])).toBe(false);
    expect(hasActiveJobs([{ status: "COMPLETED" }, { status: "FAILED" }])).toBe(false);
    expect(hasActiveJobs([{ status: "COMPLETED" }, { status: "QUEUED" }])).toBe(true);
    expect(hasActiveJobs([{ status: "RUNNING" }])).toBe(true);
  });
  it("progressPercent clamps", () => {
    expect(progressPercent(0.456)).toBe(46);
    expect(progressPercent(2)).toBe(100);
    expect(progressPercent(-1)).toBe(0);
  });
});

describe("buildAoi", () => {
  const poly = JSON.stringify({ type: "Polygon", coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] });
  it("accepts an area id", () => expect(buildAoi("abc", "")).toEqual({ ok: true, aoi: { monitored_area_id: "abc" } }));
  it("accepts Polygon and MultiPolygon", () => {
    expect(buildAoi("", poly)).toMatchObject({ ok: true });
    expect(buildAoi("", JSON.stringify({ type: "MultiPolygon", coordinates: [[[[0, 0]]]] }))).toMatchObject({ ok: true });
  });
  it("rejects invalid JSON, wrong type, empty coordinates", () => {
    expect(buildAoi("", "{nope")).toMatchObject({ ok: false, error: expect.stringContaining("valid JSON") });
    expect(buildAoi("", JSON.stringify({ type: "Point", coordinates: [0, 0] }))).toMatchObject({ ok: false });
    expect(buildAoi("", JSON.stringify({ type: "Feature", geometry: {} }))).toMatchObject({ ok: false });
    expect(buildAoi("", "null")).toMatchObject({ ok: false });
    expect(buildAoi("", JSON.stringify({ type: "Polygon", coordinates: [] }))).toMatchObject({ ok: false });
  });
  it("rejects both or neither", () => {
    expect(buildAoi("abc", poly)).toMatchObject({ ok: false });
    expect(buildAoi("", "  ")).toMatchObject({ ok: false });
  });
});

describe("buildDateRange", () => {
  it("validates order and formats", () => {
    expect(buildDateRange("2025-02-01", "2025-01-01")).toMatchObject({ ok: false });
    expect(buildDateRange("2025-01-01", "2025-01-01")).toEqual({
      ok: true, start_date: "2025-01-01T00:00:00Z", end_date: "2025-01-01T23:59:59Z",
    });
    expect(buildDateRange("", "")).toEqual({ ok: true, start_date: undefined, end_date: undefined });
  });
});

describe("data services", () => {
  const call = (f: ReturnType<typeof mockFetch>) => ({ url: f.mock.calls[0][0], init: f.mock.calls[0][1] });
  it("GET urls omit empty params", async () => {
    let f = mockFetch(); await listCollections({ provider: "NISAR", refresh: true });
    expect(call(f).url).toMatch(/\/data\/collections\?provider=NISAR&refresh=true$/);
    f = mockFetch(); await listDataAcquisitions({ product_type: "GUNW", status: "", maturity: "BETA", limit: 20 });
    expect(call(f).url).toMatch(/\/data\/acquisitions\?product_type=GUNW&maturity=BETA&limit=20$/);
    f = mockFetch(); await listDownloads({ offset: 0, limit: 100 });
    expect(call(f).url).toMatch(/\/data\/downloads\?offset=0&limit=100$/);
    f = mockFetch(); await listDownloads();
    expect(call(f).url).toMatch(/\/data\/downloads$/);
  });
  it("POST bodies", async () => {
    let f = mockFetch();
    await searchData({ aoi: { monitored_area_id: "a" }, dry_run: true });
    expect(call(f).url).toMatch(/\/data\/search$/);
    expect(JSON.parse(call(f).init?.body as string)).toEqual({ aoi: { monitored_area_id: "a" }, dry_run: true });
    f = mockFetch(); await createDownloads(["1", "2"]);
    expect(call(f).url).toMatch(/\/data\/downloads$/);
    expect(JSON.parse(call(f).init?.body as string)).toEqual({ acquisition_ids: ["1", "2"] });
    f = mockFetch(); await retryDownload("j1");
    expect(call(f).url).toMatch(/\/data\/downloads\/j1\/retry$/);
    f = mockFetch(); await acquireEnvironmental({ aoi: { monitored_area_id: "a" }, start_date: "s", end_date: "e", dry_run: true });
    expect(call(f).url).toMatch(/\/data\/environmental\/acquire$/);
    f = mockFetch(); await importLandslideEvents();
    expect(call(f).url).toMatch(/\/data\/landslide-events\/import$/);
    expect(JSON.parse(call(f).init?.body as string)).toEqual({ force: false });
  });
});
