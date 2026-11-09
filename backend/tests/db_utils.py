"""Test-database lifecycle helpers. Destructive calls are guarded by the `_test` name suffix."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url

from app.settings import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def assert_test_database(name: str | None) -> str:
    assert name is not None and name.endswith("_test"), (
        f"refusing to touch database {name!r}: test databases must end in '_test'"
    )
    return name


def url_for(database: str) -> str:
    """Test-server URL (password included) pointing at `database`."""
    return (
        make_url(settings.test_database_url)
        .set(database=database)
        .render_as_string(hide_password=False)
    )


def drop_database(server: Engine, name: str) -> None:
    quoted = server.dialect.identifier_preparer.quote(assert_test_database(name))
    with server.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))


def recreate_database(server: Engine, name: str) -> None:
    drop_database(server, name)
    quoted = server.dialect.identifier_preparer.quote(name)
    with server.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {quoted}"))


def _alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["url"] = url
    return cfg


def upgrade(url: str, revision: str = "head") -> None:
    command.upgrade(_alembic_config(url), revision)


def downgrade(url: str, revision: str) -> None:
    command.downgrade(_alembic_config(url), revision)
