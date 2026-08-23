# Backend Database Configuration

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Load the database URL from environment variables
# Load environment variables from backend/.env relative to project root
project_root = Path(__file__).resolve().parents[3]
env_path = project_root / "backend" / ".env"
load_dotenv(dotenv_path=env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set in .env")

# Create the SQLAlchemy engine (future flag enables 2.0 style)
engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

# Session factory for request-scoped sessions
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Base class for declarative models
Base = declarative_base()


