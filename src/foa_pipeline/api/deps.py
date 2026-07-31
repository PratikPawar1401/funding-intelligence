"""Dependency injection for FastAPI routes."""

from functools import lru_cache

from ..config import get_config, Config
from ..database import Database
from ..vector_index import VectorIndex


@lru_cache()
def get_app_config() -> Config:
    """Get the application configuration (cached)."""
    return get_config()


@lru_cache()
def get_vector_index() -> VectorIndex:
    """
    Load the FAISS index and embedding model once per process.

    Without this cache every semantic search re-read the index from disk and
    re-loaded the sentence-transformer model, adding seconds of latency to each
    request. Built with db=None deliberately: the index is shared across
    requests and threads, so each search is handed the request-scoped
    connection instead of holding one (SQLite connections are not shareable
    across threads).
    """
    config = get_app_config()
    index = VectorIndex(
        db=None,
        model_name=config.embedding_model,
        cache_dir=config.embeddings_cache_dir,
    )
    if index.load_index():
        index.load_model()
    return index


def get_db() -> Database:
    """Get a database connection. Should be used as a FastAPI dependency."""
    config = get_app_config()
    db = Database(config.app_db_path)
    try:
        yield db
    finally:
        db.close()
