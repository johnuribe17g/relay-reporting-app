"""Thin endpoints: parse, call the service in `app.report`, return (plans/T3-backend-api.md §1b)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Connection

from app.deps import (
    Account,
    Bounds,
    get_bounds,
    get_conn,
    get_current_account,
    get_judge_params,
    get_summary_provider,
    get_summary_settings,
)
from app.domain.models import JudgeParams
from app.report import build_accounts, build_history, build_report, build_weeks
from app.schemas import AccountOut, History, Report, SummaryOut, SummaryRequest, WeeksOut
from app.settings import SummarySettings
from app.summary.providers import Provider
from app.summary.service import summarize

router = APIRouter(prefix="/api")

Conn = Annotated[Connection, Depends(get_conn)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]
Params = Annotated[JudgeParams, Depends(get_judge_params)]
DataBounds = Annotated[Bounds, Depends(get_bounds)]
# `week` stays a string: it is parsed in `report.resolve_week`, which raises `invalid_week`.
WeekQuery = Annotated[str | None, Query()]
SummaryConfig = Annotated[SummarySettings, Depends(get_summary_settings)]
SummaryProvider = Annotated[Provider, Depends(get_summary_provider)]


@router.get("/accounts")
def list_accounts(conn: Conn) -> list[AccountOut]:
    """Every account, for the demo switcher. The one endpoint that is not account-scoped."""
    return build_accounts(conn)


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


@router.post("/summary")
def summary(
    body: SummaryRequest,
    conn: Conn,
    account: CurrentAccount,
    params: Params,
    bounds: DataBounds,
    config: SummaryConfig,
    provider: SummaryProvider,
) -> SummaryOut:
    """A short summary of the week. The report is built first, so a bad week is a 422 either way."""
    report = build_report(conn, account, body.week, params, bounds)
    return summarize(report, config, provider)
