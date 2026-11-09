"""Settings stub. Business parameters (baseline weeks, z_min, ...) arrive in T2."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://relay:relay@localhost:5433/relay"
    test_database_url: str = "postgresql+psycopg://relay:relay@localhost:5433/relay_test"
    seed_path: Path = Path("/data/seed.sql")


settings = Settings()
