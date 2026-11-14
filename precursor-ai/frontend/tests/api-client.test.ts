import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet } from "@/lib/api-client";
import { getHealth } from "@/services/system";

const BASE = "http://api.test/api/v1";

function mockFetch(impl: (url: string, init?: RequestInit) => Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn(impl));
}

afterEach(() => vi.unstubAllGlobals());

describe("apiGet", () => {
  it("returns parsed JSON and calls the configured base URL", async () => {
    const payload = { status: "ok", app_name: "PRECURSOR AI", version: "0.1.0", database: "connected" };
    mockFetch(async () => new Response(JSON.stringify(payload), { status: 200 }));
    const out = await apiGet<typeof payload>("/health", { baseUrl: BASE });
    expect(out).toEqual(payload);
    expect(fetch).toHaveBeenCalledWith(`${BASE}/health`, expect.anything());
  });

  it("maps backend error envelope to ApiError", async () => {
    mockFetch(async () => new Response(JSON.stringify({ error: { code: "not_found", message: "nope" } }), { status: 404 }));
    await expect(apiGet("/areas/x", { baseUrl: BASE })).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      code: "not_found",
      message: "nope",
    });
  });

  it("handles non-JSON error bodies", async () => {
    mockFetch(async () => new Response("<html>bad gateway</html>", { status: 502 }));
    await expect(apiGet("/health", { baseUrl: BASE })).rejects.toMatchObject({ status: 502, code: "http_error" });
  });

  it("reports network failure", async () => {
    mockFetch(async () => {
      throw new TypeError("failed to fetch");
    });
    await expect(apiGet("/health", { baseUrl: BASE })).rejects.toMatchObject({ code: "network_error" });
  });

  it("times out slow requests", async () => {
    mockFetch(
      (_url, init) =>
        new Promise((_res, rej) => {
          init?.signal?.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError")));
        }),
    );
    const err = await apiGet<never>("/health", { baseUrl: BASE, timeoutMs: 20 }).catch((e: unknown) => e as ApiError);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("timeout");
  });

  it("rejects invalid JSON on success status", async () => {
    mockFetch(async () => new Response("not json", { status: 200 }));
    await expect(apiGet("/health", { baseUrl: BASE })).rejects.toMatchObject({ code: "parse_error" });
  });
});

describe("services", () => {
  it("getHealth hits /health", async () => {
    mockFetch(async (url) => new Response(JSON.stringify({ url }), { status: 200 }));
    const out = (await getHealth()) as unknown as { url: string };
    expect(out.url).toMatch(/\/health$/);
  });
});
