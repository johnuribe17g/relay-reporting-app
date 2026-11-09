from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.engine import make_url

from app.settings import settings
from tests import db_utils


@pytest.fixture(scope="session")
def server_engine() -> Iterator[Engine]:
    """Engine on the server's maintenance database ('postgres'). Never the app database."""
    url = make_url(settings.test_database_url).set(database="postgres")
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def test_engine(server_engine: Engine) -> Iterator[Engine]:
    """`relay_test`, dropped and recreated each run, then migrated to head from scratch.

    It is left in place after the run so a failure can be inspected; the next run recreates it.
    """
    name = db_utils.assert_test_database(make_url(settings.test_database_url).database)
    db_utils.recreate_database(server_engine, name)
    db_utils.upgrade(db_utils.url_for(name))
    engine = create_engine(db_utils.url_for(name))
    yield engine
    engine.dispose()


@pytest.fixture
def conn(test_engine: Engine) -> Iterator[Connection]:
    """One connection per test inside a transaction that is always rolled back."""
    with test_engine.connect() as connection:
        connection.begin()
        yield connection
        connection.rollback()


@pytest.fixture
def migrations_db_url(server_engine: Engine) -> Iterator[str]:
    """Empty throwaway database for tests that migrate up and down (never `relay_test`)."""
    name = "relay_migrations_test"
    db_utils.recreate_database(server_engine, name)
    yield db_utils.url_for(name)
    db_utils.drop_database(server_engine, name)
