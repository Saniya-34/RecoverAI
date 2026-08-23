"""
backend/app/database/__init__.py

SQLAlchemy 2.x database configuration.

Exports:
    engine       — shared Engine instance (pool_pre_ping enabled)
    SessionLocal — session factory (autoflush=False, autocommit=False)
    Base         — declarative base for all ORM models
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ── Environment ───────────────────────────────────────────────────────────────
# Resolve backend/.env relative to the project root so this module works
# whether it is imported from the project root or from within backend/.
_project_root = Path(__file__).resolve().parents[3]
load_dotenv(dotenv_path=_project_root / "backend" / ".env")

DATABASE_URL: str = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Copy backend/.env.example → backend/.env and fill in the value."
    )

# ── Engine ────────────────────────────────────────────────────────────────────
# SQLAlchemy 2.x: future=True is the default and the flag is deprecated.
# pool_pre_ping recycles stale connections after a DB restart.
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

# ── Session factory ───────────────────────────────────────────────────────────
# autoflush=False  — we flush explicitly inside service methods.
# autocommit=False — transactions are managed by the route/service layer.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,   # avoids lazy-load errors after commit
)


# ── Declarative base ──────────────────────────────────────────────────────────
# SQLAlchemy 2.x style: subclass DeclarativeBase instead of calling
# declarative_base() which is deprecated.
class Base(DeclarativeBase):
    """
    Base class for all ORM models.

    All model classes must inherit from this Base so that
    Base.metadata contains their table definitions for Alembic.
    """
