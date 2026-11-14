# General rules

- Follow the existing architecture (API -> services -> repositories -> models; `ai_engine` never imports FastAPI). Reuse existing config, DB session, exception envelope and naming.
- No unnecessary rewrites. Change only what the task needs; do not touch working code of earlier phases.
- Prefer modular, small, testable units. No speculative abstraction.
- Add a dependency only with a stated justification (and record it in the changelog).
- Run the relevant tests after every change and report the real result; if something was not run, say so.
- Update documentation when implementation changes (see documentation.md).
- Do not implement future phases early. Do not start the next phase automatically.
- Destructive or outward-facing actions (deleting data, downloads, logins, pushing) need explicit user approval.
