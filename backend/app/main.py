"""
backend/app/main.py

FastAPI application factory.

Registers:
    - CORS middleware (permits the React dev server at localhost:5173)
    - /health          (Stage 1)
    - /api/events      (Stage 4 — merchant event ingestion)
    - /api/recovery-cases  (Stage 4 — recovery case read API)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Side-effect import: registers all ORM models with Base.metadata so
# Alembic can introspect the schema without extra configuration.
from . import models as _models  # noqa: F401

from .api.routes import agent, audit, dashboard, events, health, recovery_cases


def create_app() -> FastAPI:
    """
    Application factory.

    Using a factory function (instead of a module-level app object)
    makes the app easier to test and keeps configuration explicit.
    """
    app = FastAPI(
        title="RecoverAI API",
        version="0.4.0",
        description=(
            "Deterministic revenue-recovery system for Razorpay merchants. "
            "Stage 4: merchant event ingestion and revenue-at-risk detection."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(dashboard.router)
    app.include_router(events.router)
    app.include_router(recovery_cases.router)
    app.include_router(audit.router)
    app.include_router(agent.router)

    return app


# Module-level app instance used by uvicorn and the test client.
app = create_app()
