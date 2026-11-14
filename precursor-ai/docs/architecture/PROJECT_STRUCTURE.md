# Project structure

Verified from the repository on 2026-11-14.

```
precursor-ai/
  CLAUDE.md  CHANGELOG.md  README.md  docker-compose.yml  .env.example  (.env gitignored)
  .claude/rules/*  .claude/skills/precursor-workflow/
  backend/
    app/
      main.py                  create_app + lifespan
      core/                    config, exceptions, logging, geo_env
      api/v1/                  areas, acquisitions, health, system, router
      api/v1/insar.py          Phase 3 router (/insar)
      api/v1/environmental.py  Phase 4 router (/environmental)
      api/v1/data/             Phase 2 routers (collections, search, acquisitions, downloads,
                               environmental, landslide_events, status, deps)
      models/                  area, satellite_source, satellite_acquisition (Phase 1);
                               data_collection, data_acquisition, download_job, landslide_event (Phase 2); insar (Phase 3)
      repositories/            base, area, satellite
      schemas/                 Pydantic contracts (+ data_acquisition)
      services/                area_service; data_acquisition/ (providers/, download_manager,
                               validation_service, metadata_service, search_service,
                               orchestrator, authentication, aoi, cmr, storage, registry, ...)
      services/insar/          Phase 3: adapters/ inspection phase_to_displacement coherence interferogram
                               velocity processing outputs storage runs external synthetic
      services/environmental/  Phase 4: raster/ (incl. reference_grid.py) dem/ rainfall/ providers/ soil/ land_cover/
                               smap/ lithology/ vegetation/ distances/ seismic/ features/ pipeline/
                               manifest external_inputs preview queries catalog storage types synthetic_raster
      services/features_cv/    Phase 5: tiling terrain texture change registry schema stack pipeline
                               dataset dataset_run events export types; CLI: python -m app.services.features_cv
      api/v1/features_cv.py    Phase 5 read-only router (/features-cv)
      cli/                     python -m app.cli
    alembic/versions/          0001_initial_schema, 0002_data_acquisition, 0003_insar_processing, 0004_environmental, 0005 (temporal_kind, aligned_file_path, reference_grid)
    tests/                     Phase 1 tests; data_acquisition/ (mocks); insar/ (synthetic); environmental/ (synthetic); features_cv/ (synthetic); manual/ (live, skipped by default)
  frontend/
    app/                       / (landing), dashboard/{areas,risk-map,predictions,alerts,analytics,settings,satellite-data,data/*,insar,environmental}
    components/                cinematic/, dashboard/, data/, layout/, maps/ ...
    lib/ services/ hooks/ types/ tests/ scripts/
  ai_engine/                   READMEs only: preprocessing, insar, computer_vision, risk_assessment, explainability, data_acquisition
  data/                        aoi/, raw/{nisar,nasadem,gpm,smap,landslide_catalog}, metadata/, processed/, external/, samples/
  models/                      checkpoints/, evaluation/ (.gitkeep only)
  docs/                        project/ architecture/ adr/ phases/ scientific/ development/ + Phase 1-2 guides
  notebooks/ scripts/ tests/   .gitkeep only
```

`ai_engine/data_acquisition` is a placeholder; the real Phase 2 code lives in `backend/app/services/data_acquisition/`.
