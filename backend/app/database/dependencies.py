"""
backend/app/database/dependencies.py

FastAPI dependency for SQLAlchemy sessions.

Usage in a route:
    from backend.app.database.dependencies import get_db
    ...
    def my_route(db: Session = Depends(get_db)):
        ...
"""

from collections.abc import Generator

from sqlalchemy.orm import Session

from . import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Yield a database session for the duration of one HTTP request.

    The session is always closed in the finally block regardless of
    whether the request succeeded or raised an exception.
    Transaction management (begin/commit/rollback) is the responsibility
    of the route or service layer — this dependency only manages the
    session lifecycle.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
