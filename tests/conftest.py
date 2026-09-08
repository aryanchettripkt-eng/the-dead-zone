"""Pytest configuration and deterministic database test harness for SETU-DRR.

P0.6: Deterministic Backend DB Test Environment.

Provides:
- Automatic test categorization: integration and performance tests are marked as `db`.
- Isolated test database lifecycle targeting a dedicated test database (e.g. `setu_test`).
- Clean separation: unit and contract tests run in-memory without PostgreSQL dependencies.
- Canonical migration execution (001_ through 012_) via `infra.apply_migrations`.
- Deterministic pilot data seeding (SEED=42) via `pipeline.jobs.seed_pilot_data`.
- Reconfigured application settings and FastAPI dependencies for test isolation.
- Clear, actionable failure diagnostics when PostgreSQL is unreachable (no silent skips).
"""

from __future__ import annotations

import os
import sys
import shutil
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Generator

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in [REPO_ROOT, REPO_ROOT / "core" / "src", REPO_ROOT / "api" / "src", REPO_ROOT / "pipeline" / "src"]:
    p_str = str(p)
    if p_str in sys.path:
        sys.path.remove(p_str)
    sys.path.insert(0, p_str)

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import settings
from infra.apply_migrations import apply_migrations
from pipeline.jobs.seed_pilot_data import seed_database


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "db: mark test as requiring a PostgreSQL/PostGIS test database"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark integration and performance tests as requiring the database."""
    for item in items:
        file_path = str(item.fspath).replace("\\", "/")
        if "tests/integration" in file_path or "tests/performance" in file_path:
            item.add_marker(pytest.mark.db)


@pytest.fixture(autouse=True)
def _reset_global_model_registry():
    """Ensure global model_registry state does not leak across tests."""
    yield
    from core.ml.registry import model_registry
    model_registry.reset()


@pytest.fixture(autouse=True)
def _reset_global_login_rate_limiter():
    """Ensure login rate limiter state does not leak across tests."""
    from api.dependencies import get_login_rate_limiter
    limiter = get_login_rate_limiter()
    limiter.reset()
    yield
    limiter.reset()


def mask_db_url(url: str) -> str:
    """Mask credentials in connection URL for safe diagnostic output."""
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.password:
            netloc = f"{parsed.username}:****@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urllib.parse.urlunsplit(
                (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
            )
    except Exception:
        pass
    return url


def resolve_test_database_urls() -> tuple[str, str, str, str]:
    """Resolves database connection URLs for testing.
    
    Returns:
        tuple: (server_conninfo, test_conninfo, test_sqla_url, test_db_name)
    """
    explicit = os.environ.get("TEST_DATABASE_URL") or settings.TEST_DATABASE_URL
    if explicit:
        raw_url = explicit
    else:
        raw_url = settings.DIRECT_DATABASE_URL or settings.DATABASE_URL
        if not raw_url:
            raw_url = "postgresql://setu:setu@localhost:5432/setu"

    parsed = urllib.parse.urlsplit(raw_url)
    db_name = parsed.path.lstrip("/") or "setu"

    # Always isolate into a test database (e.g. setu_test) to protect developer/staging databases
    if db_name.endswith("_test"):
        test_db_name = db_name
    else:
        test_db_name = "setu_test"

    # Maintenance database used to check/create the test database
    if parsed.hostname in ("localhost", "127.0.0.1", None):
        server_db = "postgres"
    else:
        server_db = db_name if db_name != test_db_name else "postgres"

    server_url = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, f"/{server_db}", parsed.query, parsed.fragment)
    )
    test_url = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, f"/{test_db_name}", parsed.query, parsed.fragment)
    )

    # Normalize to psycopg conninfo (plain postgresql://)
    server_conninfo = server_url
    for s in ("postgresql+psycopg://", "postgresql+asyncpg://"):
        if server_conninfo.startswith(s):
            server_conninfo = server_conninfo.replace(s, "postgresql://", 1)

    test_conninfo = test_url
    for s in ("postgresql+psycopg://", "postgresql+asyncpg://"):
        if test_conninfo.startswith(s):
            test_conninfo = test_conninfo.replace(s, "postgresql://", 1)

    # Normalize to SQLAlchemy URL (postgresql+psycopg://)
    test_sqla_url = test_url
    if test_sqla_url.startswith("postgresql://"):
        test_sqla_url = test_sqla_url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif test_sqla_url.startswith("postgres://"):
        test_sqla_url = test_sqla_url.replace("postgres://", "postgresql+psycopg://", 1)

    return server_conninfo, test_conninfo, test_sqla_url, test_db_name


def ensure_database_ready(server_conninfo: str, test_conninfo: str, test_db_name: str) -> None:
    """Verifies database connectivity, provisions test DB, and enables extensions."""
    connected = False

    # 1. Quick probe of test database directly
    try:
        with psycopg.connect(test_conninfo, connect_timeout=4) as conn:
            connected = True
    except Exception:
        # Fall back to probing server maintenance database
        try:
            with psycopg.connect(server_conninfo, connect_timeout=4) as conn:
                connected = True
        except Exception:
            connected = False

    # 2. If not reachable, attempt local Docker startup if available
    if not connected:
        parsed = urllib.parse.urlsplit(test_conninfo)
        is_local = parsed.hostname in ("localhost", "127.0.0.1", None)
        docker_bin = shutil.which("docker")

        if is_local and docker_bin:
            repo_root = Path(__file__).resolve().parents[1]
            compose_file = repo_root / "infra" / "docker-compose.yml"
            if compose_file.exists():
                try:
                    subprocess.run(
                        [docker_bin, "compose", "-f", str(compose_file), "up", "-d", "db"],
                        check=True,
                        capture_output=True,
                        timeout=30,
                    )
                    # Poll for readiness
                    for _ in range(30):
                        time.sleep(1)
                        try:
                            with psycopg.connect(server_conninfo, connect_timeout=2) as conn:
                                connected = True
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

        # If still not connected, fail clearly with actionable message (DO NOT skip)
        if not connected:
            masked = mask_db_url(test_conninfo)
            pytest.fail(
                f"\n[DATABASE UNAVAILABLE] Could not connect to PostgreSQL at {masked}.\n\n"
                "To run database-dependent tests, PostgreSQL with PostGIS and H3 extensions is required:\n"
                "  1. If using Docker: run `docker compose -f infra/docker-compose.yml up -d db`\n"
                "  2. Or specify a reachable test database: set TEST_DATABASE_URL=postgresql://user:pass@host:port/dbname\n"
                "  3. Required extensions: postgis, postgis_raster, h3, h3_postgis.\n",
                pytrace=False,
            )

    # 3. Create test database if it does not already exist
    try:
        with psycopg.connect(test_conninfo, autocommit=True, connect_timeout=4) as conn:
            pass
    except Exception:
        try:
            with psycopg.connect(server_conninfo, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (test_db_name,))
                    if not cur.fetchone():
                        cur.execute(f'CREATE DATABASE "{test_db_name}";')
        except Exception as e:
            pytest.fail(
                f"\n[DATABASE SETUP FAILED] Failed to create test database '{test_db_name}': {e}",
                pytrace=False,
            )

    # 4. Enable required extensions in the test database
    try:
        with psycopg.connect(test_conninfo, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS postgis_raster;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS h3;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS h3_postgis;")
    except Exception as e:
        pytest.fail(
            f"\n[EXTENSION SETUP FAILED] Failed to initialize extensions in '{test_db_name}': {e}\n"
            "Ensure the PostgreSQL instance has PostGIS and H3 packages installed.",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def db_environment():
    """Session-scoped fixture providing an isolated, migrated, and seeded test database."""
    server_conninfo, test_conninfo, test_sqla_url, test_db_name = resolve_test_database_urls()

    # 1. Ensure DB running, created, and extensions enabled
    ensure_database_ready(server_conninfo, test_conninfo, test_db_name)

    # 2. Apply canonical migrations (001_ through 011_)
    apply_migrations(test_conninfo)

    # 3. Deterministically seed pilot fixtures
    seed_database(test_sqla_url)

    # 4. Reconfigure settings and API dependencies to target the test database
    original_db_url = settings.DATABASE_URL
    original_direct_url = settings.DIRECT_DATABASE_URL

    settings.DATABASE_URL = test_conninfo
    settings.DIRECT_DATABASE_URL = test_conninfo

    from api import dependencies
    from api.main import app

    old_engine = dependencies.engine
    test_engine = create_engine(
        test_sqla_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    test_session_maker = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    dependencies.engine = test_engine
    dependencies.SessionLocal = test_session_maker

    def _test_get_db() -> Generator[Session, None, None]:
        db = test_session_maker()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[dependencies.get_db] = _test_get_db

    yield {
        "engine": test_engine,
        "session_maker": test_session_maker,
        "conninfo": test_conninfo,
        "sqlalchemy_url": test_sqla_url,
        "db_name": test_db_name,
    }

    # Teardown / restore
    app.dependency_overrides.pop(dependencies.get_db, None)
    test_engine.dispose()
    dependencies.engine = old_engine
    settings.DATABASE_URL = original_db_url
    settings.DIRECT_DATABASE_URL = original_direct_url


@pytest.fixture(autouse=True)
def _auto_db_environment(request):
    """Automatically activates db_environment only for tests marked with `db`."""
    if request.node.get_closest_marker("db"):
        return request.getfixturevalue("db_environment")
    return None


@pytest.fixture(scope="function")
def db_session(db_environment) -> Generator[Session, None, None]:
    """Provides an isolated database session that rolls back on completion."""
    session = db_environment["session_maker"]()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="session")
def db_engine(db_environment):
    """Provides the test database SQLAlchemy engine."""
    return db_environment["engine"]
