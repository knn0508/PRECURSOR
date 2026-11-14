# Phase 9: Interactive Geospatial Dashboard (early-warning workspace)

Status: **NOT_STARTED** (scope defined 2026-11-14; minimal test pages exist from Phases 2-4). Roadmap: [ROADMAP](../project/ROADMAP.md). Executable brief: [Prompts.md](../../Prompts.md) (Phase 9).

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
Minimal pages only (`/dashboard/insar`, `/dashboard/environmental`). Full dashboard not started.

## Constraints
[frontend.md](../../.claude/rules/frontend.md), [scientific-integrity.md](../../.claude/rules/scientific-integrity.md).

## Known limitations
No real prediction can be displayed until a model is registered through the ML slot.

## Dependencies
Previous: Phases 2-8. Following: Phase 10.
