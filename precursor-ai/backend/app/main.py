import app.core.geo_env  # noqa: F401  (must run before any geo library)
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        from app.api.v1.data.deps import get_orchestrator
        from app.services.data_acquisition.storage import ensure_layout

        ensure_layout(get_settings().data_root)
        n = get_orchestrator().recover_stale_jobs()
        if n:
            log.warning("marked %d interrupted download job(s) FAILED; retry to resume", n)
    except Exception:  # DB or disk may be down; the API must still start
        log.warning("startup recovery skipped", exc_info=True)
    try:
        from app.api.v1.insar import get_insar_service
        from app.services.insar.storage import ensure_layout as insar_layout

        insar_layout(get_settings().data_root)
        n = get_insar_service().recover_stale_runs()
        if n:
            log.warning("marked %d interrupted InSAR run(s) FAILED", n)
    except Exception:
        log.warning("insar startup recovery skipped", exc_info=True)
    try:
        from app.api.v1.environmental import get_env_service

        n = get_env_service().recover_stale_runs()
        if n:
            log.warning("marked %d interrupted environmental run(s) FAILED", n)
    except Exception:
        log.warning("environmental startup recovery skipped", exc_info=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="PRECURSOR AI: SAR-based early landslide risk platform (Phase 1 foundation).",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    logging.getLogger(__name__).info("Started %s v%s (%s)", settings.app_name, settings.app_version, settings.app_env)
    return app


app = create_app()
