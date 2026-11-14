# ADR-0002: Defer all ML/DL to a separately authorized phase

- Status: ACCEPTED (clarified by [ADR-0008](ADR-0008-ml-slot-and-labelled-mock-frontend.md): reserved ML slot and labelled frontend mock; decision below unchanged)
- Date: 2026-11-14 (user policy)

## Context
The risk engine is a roadmap goal, but trustworthy ML needs validated input data and a reviewed pipeline. Premature or fake models would present unvalidated numbers as science.

## Decision
All ML/DL models remain placeholders throughout the current 10-phase roadmap. No training, fine-tuning, real inference, fabricated risk scores/predictions, or hardcoded/rule-based substitutes. Allowed: deterministic scientific processing and ML interfaces/schemas/service contracts. Real ML requires a separate phase, authorized explicitly after the roadmap is complete and reviewed.

## Alternatives considered
Early baseline/demo models (rejected: risk of presenting synthetic output as prediction).

## Consequences
Phases 7-8 deliver contracts, not predictions. UI risk values stay N/A. Every phase prompt must repeat the policy.

## Related
See also [ADR-0009](ADR-0009-ml-development-track.md) (separate, isolated ML track authorized 2026-11-15). 
[ADR-0008](ADR-0008-ml-slot-and-labelled-mock-frontend.md), [scientific-integrity.md](../../.claude/rules/scientific-integrity.md), [ROADMAP](../project/ROADMAP.md)
