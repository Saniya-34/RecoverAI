"""
backend/app/main.py

FastAPI application factory.

Registers:
    - CORS middleware (permits the React dev server at localhost:5173)
    - /             → redirect to /docs
    - /health       (Stage 1)
    - /api/dashboard/summary   (Stage 6)
    - /api/events              (Stage 4)
    - /api/recovery-cases      (Stage 4)
    - /api/recovery-cases/{id}/audit  (Stage 6)
    - /api/recovery-cases/{id}/run-agent (Stage 5)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response

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
        version="0.6.0",
        description=(
            "AI-powered revenue-recovery system for merchants. "
            "Stages 1–6: event ingestion, risk detection, LangGraph agent, dashboard."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",   # Vite dev server
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Root redirect — visiting / in the browser goes to /docs ──────────────
    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/docs")

    # ── Suppress favicon 404 in browser ──────────────────────────────────────
    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

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