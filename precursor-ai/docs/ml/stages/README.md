# ML stages

One spec per stage of the ML track ([ADR-0009](../../adr/ADR-0009-ml-development-track.md)). Each has Scope, Out of scope, Gate and Acceptance (done when). Executable prompts: [Prompts.md](../../../Prompts.md). Live status: [ML_STATUS](../ML_STATUS.md).

| Stage | Title | User gate |
|---|---|---|
| [M0](M0.md) | ML track governance and workspace | none |
| [M1](M1.md) | Problem definition, dataset discovery and feasibility | USER APPROVAL REQUIRED before M2 (study design, regions, exact download list) |
| [M2](M2.md) | Data acquisition (approved files only) | none after the M1 approval; stops if sizes or auth deviate from the approved list |
| [M3](M3.md) | Preprocessing and harmonization | none |
| [M4](M4.md) | Data cleaning and quality control | none |
| [M5](M5.md) | Exploratory data analysis | USER REVIEW REQUIRED (tasks, model families, compute budget) |
| [M6](M6.md) | Feature engineering, selection and final splits | none |
| [M7](M7.md) | Baselines and model training | USER APPROVAL REQUIRED (compute and deep-model dependency before training; frozen candidates before M8) |
| [M8](M8.md) | Evaluation, calibration, uncertainty and explainability | none to start; M9 needs the user review of these results |
| [M9](M9.md) | Packaging, model card and handoff | USER DECISION REQUIRED (integration into the roadmap is a separate step) |
