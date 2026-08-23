import os
import pytest
from sqlalchemy import text
from backend.app.database import engine

def test_connection():
    """Simple connectivity check – runs SELECT 1 against the DB."""
    assert os.getenv("DATABASE_URL"), "DATABASE_URL must be set for the test"
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
