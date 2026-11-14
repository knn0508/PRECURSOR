# ADR-0003: NASA provider abstraction, single CMR seam, in-process jobs

- Status: ACCEPTED
- Date: 2026-11-14 (Phase 2)

## Context
Phase 2 must search/download from several NASA/ASF sources without coupling to one library, without live calls in tests, and without fabricating availability.

## Decision
- `DataProvider` interface (`providers/base.py`); separate providers per dataset; `registry.build_providers` honours `ENABLE_*`.
- All CMR access through `cmr.py` (earthaccess, anonymous search); this is the one seam tests mock. ASF provider is a search-only fallback.
- Search is anonymous; Earthdata credentials only for downloads (`EarthdataAuthenticationService`).
- Downloads run in an in-process `ThreadPoolExecutor` (`MAX_CONCURRENT_DOWNLOADS`); interrupted jobs are marked FAILED at startup and can be retried (resume via `.part` + Range).
- State advances only on evidence; `VALIDATED` = file integrity only.

## Alternatives considered
Celery/Redis or other external queue (deferred: unnecessary infrastructure at this stage, accepted cost: jobs lost on restart, no scheduler). Direct library calls in route handlers (rejected: untestable, violates layering).

## Consequences
Easy mocking; per-provider failure isolation; no durable queue. Revisit if long-running processing (Phase 3+) needs one.

## Related
[phase-2-data-acquisition.md](../phase-2-data-acquisition.md), [DATA_PIPELINE](../architecture/DATA_PIPELINE.md)
