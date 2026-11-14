# Architecture Decision Records

One file per important technical decision: ID, title, date, status (PROPOSED / ACCEPTED / DEPRECATED / SUPERSEDED), context, decision, alternatives, consequences, related docs. No ADRs for trivial details. Never edit an accepted ADR's decision; supersede it with a new one.

| ID | Title | Status |
|---|---|---|
| [0001](ADR-0001-initial-architecture.md) | Initial technology stack and layering | ACCEPTED |
| [0002](ADR-0002-ml-deferral.md) | Defer all ML/DL to a separately authorized phase | ACCEPTED |
| [0003](ADR-0003-nasa-provider-abstraction.md) | NASA provider abstraction, single CMR seam, in-process jobs | ACCEPTED |
| [0004](ADR-0004-insar-placement-and-strategy.md) | InSAR code in the backend; delegate heavy SAR processing | ACCEPTED |
| [0005](ADR-0005-environmental-integration-design.md) | Environmental integration design | ACCEPTED |
| [0006](ADR-0006-stack-manifest-and-reference-grid.md) | Stack manifest and common reference grid | ACCEPTED |
| [0007](ADR-0007-feature-extraction-and-labelled-dataset.md) | Feature extraction, labelled sample dataset and their dependencies (revises the scipy rejection in 0005) | ACCEPTED |
| [0008](ADR-0008-ml-slot-and-labelled-mock-frontend.md) | ML slot and labelled frontend mock predictions, no ML (clarifies 0002) | ACCEPTED |
| [0009](ADR-0009-ml-development-track.md) | ML development track authorized, isolated from the 10 phases (supplements 0002, 0008) | ACCEPTED |
