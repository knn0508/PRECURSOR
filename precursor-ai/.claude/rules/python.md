---
paths:
  - "backend/**/*.py"
  - "ai_engine/**/*.py"
---

# Python rules

- Follow existing conventions (see `backend/app/`). Type-hint public functions.
- Validate every external input (user input, NASA responses, file contents) at the boundary.
- Handle errors explicitly with the project's exception types; no bare `except`, no swallowed failures. Never put secrets in exception messages or logs.
- Keep scientific calculations as pure, unit-testable functions separate from I/O.
- No unnecessary abstractions. Import `app.core.geo_env` before any geo library.
- Tests: pytest under `backend/tests/`. Mock NASA at the single seam `services/data_acquisition/cmr.py`; never hit live services in automated tests.
