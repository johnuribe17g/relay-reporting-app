from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.settings import settings


@lru_cache
def get_engine() -> Engine:
    """Sync engine for the app database (also used as a FastAPI dependency)."""
    return create_engine(settings.database_url, pool_pre_ping=True)
