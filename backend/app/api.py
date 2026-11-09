"""Thin endpoints: parse, call the service in `app.report`, return (plans/T3-backend-api.md §1b)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Connection, text

from app.deps import Account, Bounds, get_bounds, get_conn, get_current_account, get_judge_params
from app.domain.models import JudgeParams
from app.report import build_history, build_report, build_weeks
from app.schemas import AccountOut, History, Report, WeeksOut

router = APIRouter(prefix="/api")

Conn = Annotated[Connection, Depends(get_conn)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]
Params = Annotated[JudgeParams, Depends(get_judge_params)]
DataBounds = Annotated[Bounds, Depends(get_bounds)]
# `week` stays a string: it is parsed in `report.resolve_week`, which raises `invalid_week`.
WeekQuery = Annotated[str | None, Query()]


@router.get("/accounts")
def list_accounts(conn: Conn) -> list[AccountOut]:
    """Every account, for the demo switcher. The one endpoint that is not account-scoped."""
    rows = conn.execute(text("SELECT id, name, timezone FROM accounts ORDER BY id")).all()
    return [AccountOut(id=r[0], name=r[1], timezone=r[2]) for r in rows]


@router.get("/weeks")
def weeks(conn: Conn, account: CurrentAccount, params: Params, bounds: DataBounds) -> WeeksOut:
    return build_weeks(conn, account, params, bounds)


@router.get("/report")
def report(
    conn: Conn,
    account: CurrentAccount,
    params: Params,
    bounds: DataBounds,
    week: WeekQuery = None,
) -> Report:
    return build_report(conn, account, week, params, bounds)


@router.get("/locations/{location}/history")
def location_history(
    location: str,
    conn: Conn,
    account: CurrentAccount,
    params: Params,
    bounds: DataBounds,
    week: WeekQuery = None,
) -> History:
    return build_history(conn, account, location, week, params, bounds)
