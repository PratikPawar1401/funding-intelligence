"""Dependency injection for FastAPI routes."""

from functools import lru_cache
from pathlib import Path

from ..config import get_config, Config
from ..database import Database


@lru_cache()
def get_app_config() -> Config:
    """Get the application configuration (cached)."""
    return get_config()


def get_db() -> Database:
    """Get a database connection. Should be used as a FastAPI dependency."""
    config = get_app_config()
    db = Database(config.app_db_path)
    try:
        yield db
    finally:
        db.close()
