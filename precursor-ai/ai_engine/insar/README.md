# insar

**Implemented in the backend, not here.** Phase 3 InSAR code lives in `backend/app/services/insar/` (the Docker backend image only contains `backend/`; see docs/adr/ADR-0004-insar-placement-and-strategy.md). This folder stays a placeholder.

Scientific constraint: LOS displacement is derived from interferometric **phase**. It must never be conflated with amplitude/intensity change detection. Report LOS direction, reference point and uncertainty with every product. See docs/scientific/INSAR_METHODOLOGY.md.
