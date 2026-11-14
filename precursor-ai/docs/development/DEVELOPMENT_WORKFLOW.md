# Development workflow

Session workflow, canonical text: `.claude/skills/precursor-workflow/SKILL.md` and [CLAUDE.md](../../CLAUDE.md). Summary:

1. Start: read CLAUDE.md, PROJECT_STATUS, NEXT_STEPS, the phase doc; verify previous claims against code and tests.
2. Work only in the requested phase; keep earlier behaviour; mock NASA in tests; no downloads/login without approval.
3. End: run tests; update PROJECT_STATUS, NEXT_STEPS, TASK_LOG, CHANGELOG, phase/architecture docs; PROJECT_MEMORY only for durable facts; write the structured report (phase, work, files, tests with real results, remaining, issues, next action).

Documentation boundaries: [documentation.md](../../.claude/rules/documentation.md). Git: repository initialised with no commits yet; commit only when the user asks.
