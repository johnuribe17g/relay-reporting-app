"""FastAPI dependencies (plans/T3-backend-api.md §1a). Tests override these, never `now()`."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import Connection, Engine, text

from app.db import get_engine
from app.domain.models import JudgeParams
from app.errors import ApiError
from app.series import fetch_bounds
from app.settings import SummarySettings, report_settings, settings, summary_settings
from app.summary.providers import Provider, select_provider


@dataclass(frozen=True)
class Account:
    id: int
    name: str
    timezone: str


@dataclass(frozen=True)
class Bounds:
    """Global data start and as-of (naive UTC); both None on an empty view."""

    data_start: datetime | None
    as_of: datetime | None


def get_conn(engine: Annotated[Engine, Depends(get_engine)]) -> Iterator[Connection]:
    """One connection per request. The endpoints only read; it is rolled back on close."""
    with engine.connect() as connection:
        yield connection


def get_judge_params() -> JudgeParams:
    return report_settings.judge_params()


def get_summary_settings() -> SummarySettings:
    return summary_settings


def get_summary_provider(
    config: Annotated[SummarySettings, Depends(get_summary_settings)],
) -> Provider:
    """The effective provider: the mock unless a real adapter is configured and keyed."""
    return select_provider(config)


def get_bounds(conn: Annotated[Connection, Depends(get_conn)]) -> Bounds:
    data_start, as_of = fetch_bounds(conn)
    return Bounds(data_start=data_start, as_of=as_of)


def get_current_account(
    conn: Annotated[Connection, Depends(get_conn)],
    x_account_id: Annotated[int | None, Header(ge=1)] = None,
) -> Account:
    """The account from `X-Account-Id`, or the demo default when the header is missing.

    The account never comes from a path or query parameter; every query takes its id.
    """
    account_id = settings.demo_account_id if x_account_id is None else x_account_id
    row = conn.execute(
        text("SELECT id, name, timezone FROM accounts WHERE id = :id"), {"id": account_id}
    ).one_or_none()
    if row is None:
        raise ApiError(404, "account_not_found", f"account {account_id} does not exist")
    return Account(id=row[0], name=row[1], timezone=row[2])
