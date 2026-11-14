import { API_URL, REQUEST_TIMEOUT_MS } from "@/lib/config";
import type { ApiErrorBody } from "@/types/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number | null,
    public readonly code: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
}

/** Build "?a=1&b=2" from params, omitting undefined/null/empty values. Returns "" when nothing remains. */
export function buildQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** Typed GET against the backend. Throws ApiError for network, timeout, HTTP and parse failures. */
export const apiGet = <T>(path: string, opts: RequestOptions = {}) => request<T>("GET", path, undefined, opts);

/** Typed JSON POST; same error handling as apiGet. */
export const apiPost = <T>(path: string, body: unknown, opts: RequestOptions = {}) =>
  request<T>("POST", path, body, opts);

async function request<T>(method: string, path: string, body: unknown, opts: RequestOptions): Promise<T> {
  const url = `${opts.baseUrl ?? API_URL}${path}`;
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, opts.timeoutMs ?? REQUEST_TIMEOUT_MS);
  opts.signal?.addEventListener("abort", () => controller.abort());

  try {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(
      url,
      method === "GET"
        ? { signal: controller.signal, headers }
        : { method, signal: controller.signal, headers, body: JSON.stringify(body) },
    );
    if (!res.ok) {
      let body: Partial<ApiErrorBody> = {};
      try {
        body = await res.json();
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(
        body.error?.message ?? `Request failed (${res.status})`,
        res.status,
        body.error?.code ?? "http_error",
      );
    }
    try {
      return (await res.json()) as T;
    } catch {
      throw new ApiError("Invalid JSON in response", res.status, "parse_error");
    }
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (timedOut) throw new ApiError("Request timed out", null, "timeout");
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("Request cancelled", null, "aborted");
    }
    throw new ApiError("Cannot reach the API", null, "network_error");
  } finally {
    clearTimeout(timer);
  }
}
