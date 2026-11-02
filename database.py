"""
Database connection — SQLite for dev, swap DATABASE_URL for PostgreSQL in prod.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Dev: SQLite file in the backend directory
# Prod: set DATABASE_URL=postgresql://user:pass@host/matusmart
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(os.path.dirname(__file__), "matusmart.db")
)

# SQLite needs check_same_thread=False for async use
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
