from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

from app.db import get_engine
from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health_ok(client: TestClient, server_engine: Engine) -> None:
    app.dependency_overrides[get_engine] = lambda: server_engine
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_health_db_down(client: TestClient) -> None:
    dead = create_engine(
        "postgresql+psycopg://x:x@127.0.0.1:1/x", connect_args={"connect_timeout": 2}
    )
    app.dependency_overrides[get_engine] = lambda: dead
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "unavailable"}
