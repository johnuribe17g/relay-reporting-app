from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

from app.settings import settings


@pytest.fixture(scope="session")
def server_engine() -> Iterator[Engine]:
    """Engine on the server's maintenance database ('postgres').

    Never touches the app database. The test-database lifecycle fixtures
    (create/drop relay_test) are added with the migrations.
    """
    url = make_url(settings.test_database_url).set(database="postgres")
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    yield engine
    engine.dispose()
