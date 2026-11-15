// Browser-visible; inlined at build time by Next.js.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");
export const REQUEST_TIMEOUT_MS = 8000;

// ADR-0008 / Phase 9: labelled MOCK prediction views. OFF unless the build explicitly sets it to "true"; the default UI shows N/A.
export const USE_MOCK_PREDICTIONS = process.env.NEXT_PUBLIC_USE_MOCK_PREDICTIONS === "true";
