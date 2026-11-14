---
paths:
  - "frontend/**/*.ts"
  - "frontend/**/*.tsx"
---

# Frontend rules

- Use the existing structure: `lib/api-client.ts` -> `services/*` -> `hooks/use-api.ts` -> components. Types mirror backend schemas in `types/`.
- Keep TypeScript strict; no `any` to silence errors.
- Always distinguish real data, synthetic/demo data and predicted values in the UI. Risk cards show N/A until a real, validated source exists. The only exception is the Phase 9 MOCK mode (ADR-0008): separate fixture module, flag default OFF, persistent `MOCK DATA: NOT A PREDICTION` banner and badge, seeded, neutral palette (no red/amber/green), no export. Landing-page visuals are illustrative and must stay labelled so.
- Label data maturity (VALIDATED/PROVISIONAL/BETA) and `data_kind` (`metadata_only`/`downloaded`/`validated`) wherever shown. Do not call a catalog hit "available data".
- Every data view needs loading, empty and error states.
- Cinematic landing (`components/cinematic/`) must keep its reduced-motion / no-WebGL fallback.
- Verify with `npx tsc --noEmit`, `npm test`, `npm run lint`, `npm run build`.
