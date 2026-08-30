"""
backend/app/database/__init__.py

SQLAlchemy 2.x database configuration.

Exports:
    engine       — shared Engine instance (pool_pre_ping enabled)
    SessionLocal — session factory (autoflush=False, autocommit=False)
    Base         — declarative base for all ORM models

Environment configuration is handled centrally by backend.app.config.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.app.config import DATABASE_URL


# ── Engine ────────────────────────────────────────────────────────────────────
# SQLAlchemy 2.x uses the modern engine configuration by default.
# pool_pre_ping helps recover stale database connections.
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)


# ── Session factory ───────────────────────────────────────────────────────────
# autoflush=False  — changes are flushed explicitly by service/route code.
# autocommit=False — transactions are managed explicitly.
# expire_on_commit=False — prevents unnecessary lazy-loading after commit.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# ── Declarative base ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """
    Base class for all ORM models.

    All SQLAlchemy models inherit from this Base so that
    Base.metadata contains their table definitions for Alembic.
    """

    pass