from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import routers for side‑effects (they expose a variable named `router`)
from .api.routes import health


def get_application() -> FastAPI:
    """Create and configure the FastAPI application.

    - Enables CORS for the React dev server (`http://localhost:5173`).
    - Includes the health‑check router.
    """
    app = FastAPI(title="RecoverAI Backend", version="0.1.0")

    # CORS configuration – allow the frontend during development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(health.router)

    return app

# The ASGI app instance used by uvicorn
app = get_application()
