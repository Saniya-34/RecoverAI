"""
alembic/env.py

Alembic migration environment.

Supports both offline (SQL generation) and online (live DB) modes.
DATABASE_URL is read from backend/.env — never hardcoded.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool


# ── Project bootstrap ─────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Allows imports such as backend.app.database
sys.path.insert(0, str(PROJECT_ROOT))

# Load DATABASE_URL from:
# RecoverAI/backend/.env
load_dotenv(PROJECT_ROOT / "backend" / ".env")


# ── Application imports ────────────────────────────────────────────────────────

from backend.app.database import Base  # noqa: E402
import backend.app.models  # noqa: F401, E402


# ── Alembic configuration ─────────────────────────────────────────────────────

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ── Database URL ───────────────────────────────────────────────────────────────

def _get_database_url() -> str:
    url = os.getenv("DATABASE_URL")

    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Ensure backend/.env exists and contains a valid DATABASE_URL."
        )

    return url


# ── Offline migrations ─────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """Run migrations in offline mode."""

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
    """Run migrations against the live PostgreSQL database."""

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


# ── Entry point ────────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()