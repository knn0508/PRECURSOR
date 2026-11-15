"""Test fixtures.

DB-backed tests need a PostGIS database (TEST_DATABASE_URL, falling back to DATABASE_URL).
They run `alembic upgrade head` once, truncate tables after each test, and are SKIPPED
(never silently passed) when the database is unreachable.
"""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

if os.getenv("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from app.core.config import get_settings  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _no_real_earthdata_credentials(monkeypatch):
    """Phase 2 issue 8: live credentials in the environment made CLI tests fail. Tests that need credentials pass them explicitly."""
    monkeypatch.delenv("EARTHDATA_USERNAME", raising=False)
    monkeypatch.delenv("EARTHDATA_PASSWORD", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(get_settings().database_url, pool_pre_ping=True)
    # DB tests TRUNCATE tables. Refuse any database that is not clearly a throwaway test database, so a forgotten
    # TEST_DATABASE_URL can never wipe the development data (e.g. the discovered NASA collections).
    name = eng.url.database or ""
    if not name.startswith("precursor_t") and not os.getenv("ALLOW_TESTS_ON_ANY_DATABASE"):
        pytest.fail(
            f"refusing to run DB tests against database {name!r}: they truncate tables. Set TEST_DATABASE_URL to a throwaway "
            "database named precursor_t_<something> (or ALLOW_TESTS_ON_ANY_DATABASE=1 if you really mean it).",
            pytrace=False)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostGIS database unavailable: {exc}")
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Session:
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "TRUNCATE earthquake_events, deformation_products, insar_processing_runs, download_jobs, data_acquisitions, data_collections, landslide_events, "
                    "satellite_acquisitions, satellite_sources, monitored_areas CASCADE"
                )
            )


@pytest.fixture
def client(db) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def plain_client() -> TestClient:
    """Client with no DB dependency override (for DB-free tests)."""
    return TestClient(app, raise_server_exceptions=False)


POLYGON = {
    "type": "Polygon",
    "coordinates": [[[44.0, 40.0], [44.1, 40.0], [44.1, 40.1], [44.0, 40.1], [44.0, 40.0]]],
}


@pytest.fixture
def polygon() -> dict:
    return POLYGON
