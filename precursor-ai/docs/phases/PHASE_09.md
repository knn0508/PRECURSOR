# Phase 9: Interactive Geospatial Dashboard (early-warning workspace)

Status: **PARTIALLY_COMPLETED** (built 2026-11-15; see Implementation status). Roadmap: [ROADMAP](../project/ROADMAP.md). Executable brief: [Prompts.md](../../Prompts.md) (Phase 9).

## Objective
The unified scientific dashboard. Shows REAL, SYNTHETIC and PLACEHOLDER content with unmistakable labels. Prediction views are **labelled MOCK placeholders** because no ML model exists.

## Scope
- Map workspace: AOI draw/upload/select (any region), layer manager (opacity, legend, units, CRS, resolution, date), time slider for dynamic layers.
- Panels: satellite data inventory, acquisition/processing job monitor, InSAR displacement/velocity/coherence, terrain, rainfall and soil-moisture series (Recharts), landslides and earthquakes, dataset metadata/quality/lineage.
- Early-warning area wired to the ML slot: both a **mock path** and a **real-response path** against the Phase 7 schemas. The backend returns `MODEL_NOT_TRAINED`; the frontend swaps in a separate mock fixture module behind one flag that is **OFF by default** (the default UI keeps N/A, per the frontend rules and [ADR-0008](../adr/ADR-0008-ml-slot-and-labelled-mock-frontend.md)). Every mock element carries a persistent `MOCK DATA: NOT A PREDICTION` banner and badge, uses a seeded generator unrelated to real inputs, a neutral palette (no red/amber/green risk semantics) and cannot be exported. The real path is tested with `TEST_FIXTURE` responses and activates when the API stops returning `MODEL_NOT_TRAINED`.
- Source badges per layer: REAL_SATELLITE, REAL_DERIVED, SYNTHETIC_DEMO, STATISTICAL, MODEL_PREDICTION, PLACEHOLDER.
- Loading/empty/error states, accessibility, responsive, large-raster performance.
- Reuse existing pages (`/dashboard/insar`, `/dashboard/environmental`, Phase 2 pages) and keep the cinematic landing page untouched.

## Out of scope
Unlabelled mock values, mock data in backend/DB/API, mock presented as or derived from real results, backend science changes beyond thin read endpoints.

## Prerequisites
Phase 7 API contracts; Phase 8 panels as interfaces.

## Acceptance
vitest for helpers/state; component tests that mock layers always show banner and badge and vanish when the flag is off; `tsc`, lint, build; one real headless-browser run against the live stack, recorded honestly.

## Implementation status
**PARTIALLY_COMPLETED (2026-11-15).** New page `/dashboard/workspace` consolidates existing components (no duplicates) plus new early-warning, series and AOI-upload components. Prediction views are wired to the Phase 7/8 contracts with a mock path (flag off by default) and a real-response path (tested with `TEST_FIXTURE`, not with a real model: none exists).

| Requirement | Evidence |
|---|---|
| Workspace page, tabs: Map & layers (reused `LayerManager`), Terrain, Rainfall & series, Landslides & earthquakes, Satellite inventory, Jobs, InSAR, Metadata & lineage, Early warning | `components/workspace/workspace.tsx`, `app/dashboard/workspace/page.tsx`; existing tab components imported as is |
| AOI select + GeoJSON upload (any region) | `aoi-upload.tsx`, `lib/workspace-helpers.ts` `parseAoiGeoJson` (tests); area dropdown |
| Layer manager: opacity, legend, units, CRS, resolution, period, source badge | `layer-manager.tsx` (CRS/resolution/units line and `SourceBadge` added) |
| Source badges REAL_SATELLITE / REAL_DERIVED / SYNTHETIC_DEMO / STATISTICAL / MODEL_PREDICTION / PLACEHOLDER | `lib/source-badges.ts`, `source-badge.tsx`; layers, series panel, early-warning views |
| Early warning, default OFF flag `NEXT_PUBLIC_USE_MOCK_PREDICTIONS`: N/A view | `NotAvailableView`; live run: 2 N/A views, no mock banner |
| Mock path: separate seeded module, persistent `MOCK DATA: NOT A PREDICTION` banner + badge + watermark, neutral grey ramp, no export, uncertainty/explanation placeholders, trigger view with day slider | `lib/mock-predictions.ts`, `early-warning-views.tsx`; live run with flag on: 2 banners, 2 badges, 2 mock views, 0 amber/red/green classes |
| Real-response path (probability, class, calibration note, valid region/time, uncertainty, explanation, model-card path) activating automatically on `status: OK` | `RealView`, `resolveView`; vitest with `TEST_FIXTURE` fixtures |
| "Research prototype, not an official warning" notice | on every early-warning view and the workspace header |
| Series panel (Phase 6 indicators, synthetic badge) | `timeseries-panel.tsx` (live API lacks `/timeseries` until the next image rebuild: error state shown, verified) |
| `/dashboard/predictions` and `/dashboard/risk-map` now use the early-warning page; nav has Workspace | `early-warning-page.tsx`, `lib/navigation.ts` |

Tests (2026-11-15): frontend `tsc --noEmit` clean, `npm run lint` clean, `vitest` **107 passed in 10 files** (87 before, 20 new: view resolution, mock banner/badge present and removed when the flag is off, no amber/red/green classes in mock markup, neutral ramp, seeded determinism, real path from fixtures, calibration wording, AOI parsing, source-badge mapping), `npm run build` passes and lists `/dashboard/workspace`. Component tests render with `react-dom/server` (no browser library added).

Live headless-browser run (Chrome headless against `next dev` on :3100/:3101 and the live API on :8000; web security disabled because CORS allows only :3000; one temporary area created through the API and deleted afterwards, dev DB back to 0 areas): workspace loads with area select and upload form; Early warning tab with the flag off shows two N/A cards, the API message `No model is trained or registered...` and the notice, no mock banner; with the flag on shows two mock cards (susceptibility grid, trigger line with day slider), banner text present 6 times in the DOM (visible banner, watermark, aria labels), 2 badges, no risk colours (screenshot reviewed); Map tab shows the empty-layers state; Rainfall tab shows the empty state and, from the stale image, `Could not load series: Not Found` (expected: the running backend image predates Phase 6).

Not done / limits: **drawing an AOI on the map is not implemented** (no drawing library installed; upload and select only); the time slider exists only in the mock trigger view, because no real layer has per-date rasters; large rasters use the existing downsampled preview PNGs, no tile/COG server; the real-response view was never shown with a real model; model-card link is a path string (no endpoint serves the file); no cross-browser, real-device or Lighthouse check; Docker frontend image not rebuilt with this code; Playwright e2e belongs to Phase 10; reused pages keep their own area selectors on the Inventory, Jobs and InSAR tabs (they do not follow the workspace selection).