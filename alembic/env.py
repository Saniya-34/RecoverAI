"""
alembic/env.py

Alembic migration environment.

Supports both offline (SQL generation) and online (live DB) modes.
DATABASE_URL is read from backend/.env — never hardcoded.
"""

# ── Standard library ──────────────────────────────────────────────────────────
import os
import sys
from logging.config import fileConfig
from pathlib import Path

# ── Third-party ───────────────────────────────────────────────────────────────
from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

# ── Project bootstrap ─────────────────────────────────────────────────────────
# Add the project root to sys.path so `backend.*` imports resolve correctly
# regardless of where alembic is invoked from.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Load DATABASE_URL from backend/.env before any SQLAlchemy code runs.
load_dotenv(PROJECT_ROOT / "backend" / ".env")

# ── Application imports ───────────────────────────────────────────────────────
# DeclarativeBase lives here; Base.metadata is the source of truth for Alembic.
from backend.app.database import Base  # noqa: E402

# Side-effect: registers every ORM model with Base.metadata.
# Without this import Alembic would detect no tables and generate empty migrations.
import backend.app.models  # noqa: F401, E402

# ── Alembic configuration ─────────────────────────────────────────────────────
alembic_cfg = context.config

if alembic_cfg.config_file_name is not None:
    fileConfig(alembic_cfg.config_file_name)

target_metadata = Base.metadata


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Ensure backend/.env exists and contains a valid DATABASE_URL."
        )
    return url


# ── Offline migrations ────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Generate SQL migration scripts without a live database connection.
    Useful for reviewing changes before applying them.
    """
    context.configure(
        url=_get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online migrations ─────────────────────────────────────────────────────────

def run_migrations_online() -> None:
    """
    Apply migrations against a live PostgreSQL instance.
    Uses NullPool so connections are not cached between migration runs.
    """
    connectable = create_engine(
        _get_database_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


# ── Entry point ───────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
