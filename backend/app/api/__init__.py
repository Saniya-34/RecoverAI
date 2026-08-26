"""API package – keeps router modules tidy.
All sub‑modules should expose a FastAPI `APIRouter` named `router`.
"""

from . import routes

__all__ = ["routes"]
