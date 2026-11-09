"""Fixtures for the API tests (plans/T3-backend-api.md §2).

`make_client` overrides `get_conn` (and optionally params and bounds) and clears every override on
teardown. `seeded_conn` follows the pattern of `tests/test_seed_anchors.py`: one module-scoped
connection holding the seed inside a transaction that is rolled back, so a module that uses it must
not share a module with tests that use `conn` (the seed's TRUNCATE locks the tables until then).
"""

from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, text

from app.deps import Bounds, get_bounds, get_conn, get_judge_params
from app.domain.models import JudgeParams
from app.main import app
from app.seed import load_seed

ClientFactory = Callable[..., TestClient]


@pytest.fixture
def make_client() -> Iterator[ClientFactory]:
    def factory(
        connection: Connection,
        *,
        params: JudgeParams | None = None,
        bounds: Bounds | None = None,
    ) -> TestClient:
        app.dependency_overrides[get_conn] = lambda: connection
        if params is not None:
            app.dependency_overrides[get_judge_params] = lambda: params
        if bounds is not None:
            app.dependency_overrides[get_bounds] = lambda: bounds
        return TestClient(app)

    yield factory
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def seeded_conn(test_engine: Engine) -> Iterator[Connection]:
    with test_engine.connect() as connection:
        connection.begin()
        load_seed(connection)
        yield connection
        connection.rollback()


class Events:
    """Insert events on a connection; every event of a week lands on that week's Wednesday."""

    def __init__(self, conn: Connection) -> None:
        self.conn = conn
        self._next_id = 1

    def account(self, account_id: int, name: str, tz: str) -> None:
        self.conn.execute(
            text("INSERT INTO accounts VALUES (:id, :name, 'Test', :tz, '2025-01-01 00:00:00')"),
            {"id": account_id, "name": name, "tz": tz},
        )

    def add(
        self,
        account: int,
        location: str,
        week: date,
        *,
        calls: int = 0,
        leads: int = 0,
        appointments: int = 0,
        unknown: int = 0,
    ) -> None:
        """`week` is a Monday; events are at Wednesday 15:00 UTC plus i minutes (no duplicates).

        Chicago (CST -6) 09:00 and Denver (MST -7) 08:00: the same local week as `week`.
        """
        kinds = (
            ["call_received"] * calls
            + ["lead_created"] * leads
            + ["appointment_set"] * appointments
            + ["phone_call"] * unknown
        )
        base = datetime.combine(week + timedelta(days=2), datetime.min.time()) + timedelta(hours=15)
        for i, kind in enumerate(kinds):
            self.conn.execute(
                text(
                    "INSERT INTO activity_events VALUES "
                    "(:id, :account, :location, :type, :at, NULL, NULL)"
                ),
                {
                    "id": self._next_id,
                    "account": account,
                    "location": location,
                    "type": kind,
                    "at": base + timedelta(minutes=i),
                },
            )
            self._next_id += 1
