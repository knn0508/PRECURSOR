---
name: precursor-workflow
description: Session start/end workflow for PRECURSOR AI development. Use at the start of any development task, when asked where the project stands or what to do next, and when finishing a task that changed code, data acquisition, schema or APIs.
---

# PRECURSOR AI workflow

## Start of session
1. Read `CLAUDE.md`, `docs/project/PROJECT_STATUS.md`, `docs/project/NEXT_STEPS.md`.
2. Identify the current phase; read `docs/phases/PHASE_NN.md` and relevant `docs/architecture/*`.
3. Inspect the code the task touches. Verify earlier "done" claims against code/tests (run the relevant tests).
4. State the next task and its scope. Do not start another phase.

## During work
- Stay in scope; preserve Phase 1/2 behaviour; mock NASA in tests; no downloads or Earthdata login without user approval of specific files.
- Obey `.claude/rules/scientific-integrity.md` (ML placeholders only; no fabricated data).
- Note new issues as they appear.

## End of task
1. Run relevant tests; capture real output.
2. Update PROJECT_STATUS, NEXT_STEPS, TASK_LOG; CHANGELOG.md if meaningful; phase doc; architecture doc if design changed; PROJECT_MEMORY only for durable facts.
3. Report: current phase, work done, files changed, tests run + actual results, remaining tasks, known issues, recommended next action.
