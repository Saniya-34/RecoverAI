from fastapi import APIRouter

router = APIRouter()

@router.get("/health", tags=["health"])
async def health_check():
    """Simple health‑check endpoint used by CI/CD and dev monitors.
    Returns a JSON payload confirming the service is up.
    """
    return {"status": "ok"}
