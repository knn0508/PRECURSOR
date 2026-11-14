# Documentation rules

One source of truth per kind of information:

| File | Holds |
|---|---|
| CLAUDE.md | instructions only |
| docs/project/PROJECT_MEMORY.md | durable knowledge (decisions, lessons, constraints) |
| docs/project/PROJECT_STATUS.md | current verified state |
| docs/project/ROADMAP.md | planned 10-phase sequence |
| docs/project/TASK_LOG.md | task history |
| CHANGELOG.md (root, canonical) | meaningful product changes |
| docs/project/NEXT_STEPS.md | immediate continuation |
| docs/adr/ | why important decisions were made |
| docs/architecture/ | how the implemented system works |
| docs/phases/ | phase requirements and completion evidence |

After meaningful progress: update PROJECT_STATUS, NEXT_STEPS, TASK_LOG; CHANGELOG for meaningful changes; PROJECT_MEMORY only for durable knowledge; phase and architecture docs when scope or implementation changed.

- Status labels: NOT_STARTED, IN_PROGRESS, PARTIALLY_COMPLETED, COMPLETED, BLOCKED, NOT_VERIFIED.
- Never mark COMPLETED without evidence (code, passing test output, or a live check). Never mark a phase COMPLETED because one task finished.
- Record real test results with date and counts. Do not record expected results.
- Do not duplicate content across files; link to the canonical doc. Fix contradictions at the source.
- Existing guides (`docs/phase-2-data-acquisition.md`, `nasa-data-sources.md`, etc.) stay canonical for their topics; reference them.
