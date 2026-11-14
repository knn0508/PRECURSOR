---
paths:
  - "backend/**"
---

# Backend rules

- Follow the FastAPI layering: route handlers do HTTP only (no NASA calls, no business logic); services hold logic; repositories own DB access.
- Validate requests and responses with Pydantic schemas in `app/schemas/`. Errors use `{"error": {"code", "message", "details?"}}`.
- Schema changes go through Alembic migrations only. `alembic check` must report no drift. Do not edit applied migrations.
- Handle exceptions deliberately; never expose credentials or stack traces in responses.
- Document every API change in `docs/architecture/API_DOCUMENTATION.md` and the changelog.
- Backend tests truncate tables: run only against a throwaway database (`TEST_DATABASE_URL`), with Earthdata credentials unset.
