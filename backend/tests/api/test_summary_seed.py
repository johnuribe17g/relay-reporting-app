"""POST /api/summary on the real seed (plans/T5-ai-summary.md §2d, E1 to E6).

Real params, real `get_bounds`; only `get_conn` and the summary settings and provider are
overridden. Expected values are the T3 anchors S5/S6/S7/S11 and T4 R1/R3. Counts that depend on the
seed (flagged and not-judged locations) are taken from `/api/report` in the same test, not
hard-coded. At S3 the report showed 12 flagged locations of 15 for account 6 at 2026-06-01
(PLAN §13 says "all 15"; recorded in the plan).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.deps import get_summary_provider, get_summary_settings
from app.main import app
from app.settings import SummarySettings
from app.summary.providers import MockProvider
from tests.api.conftest import ClientFactory

R1_LINES = [
    "Week of 2026-07-20: 20 events, within the usual range (7.1 to 30.9) for this account.",
    "Site C: 12 events, higher than usual (0.8 to 10.2); +6.5 against the usual 5.5.",
]


@pytest.fixture
def api(seeded_conn: Connection, make_client: ClientFactory) -> TestClient:
    return make_client(seeded_conn)


def configure(*, enabled: bool) -> None:
    settings = SummarySettings(llm_summary_enabled=enabled)
    app.dependency_overrides[get_summary_settings] = lambda: settings
    app.dependency_overrides[get_summary_provider] = lambda: MockProvider("ok")


def post(api: TestClient, body: dict[str, Any], account: int | None = None) -> dict[str, Any]:
    headers = {} if account is None else {"X-Account-Id": str(account)}
    response = api.post("/api/summary", json=body, headers=headers)
    assert response.status_code == 200
    return response.json()  # type: ignore[no-any-return]


def counts(api: TestClient, account: int, week: str) -> tuple[list[dict[str, Any]], int, int]:
    report = api.get(f"/api/report?week={week}", headers={"X-Account-Id": str(account)}).json()
    rows = report["locations"]
    flagged = [r for r in rows if r["verdict"] in ("higher", "lower")]
    unjudged = [r for r in rows if r["verdict"] in ("too_quiet", "not_enough_history")]
    return flagged, len(flagged), len(unjudged)


def test_e1_account_15_flag_off(api: TestClient) -> None:
    configure(enabled=False)
    body = post(api, {"week": "2026-07-20"})
    assert (body["source"], body["reason"], body["headline"]) == ("template", "disabled", None)
    assert body["text"] == "\n".join(R1_LINES)


def test_e2_account_15_flag_on_mock(api: TestClient) -> None:
    configure(enabled=True)
    body = post(api, {"week": "2026-07-20"})
    assert (body["source"], body["reason"], body["provider"]) == ("ai", None, "mock")
    assert body["headline"] == (
        "A single-location pattern: Site C is higher than usual "
        "and the rest of the account looks normal."
    )
    assert body["text"] == "\n".join(R1_LINES)


@pytest.mark.parametrize("enabled", [False, True])
def test_e3_account_20_has_nothing_to_summarize_in_both_flag_states(
    api: TestClient, enabled: bool
) -> None:
    configure(enabled=enabled)
    body = post(api, {}, account=20)
    assert body["week"] is None and body["headline"] is None
    assert (body["source"], body["reason"]) == ("template", "nothing_to_summarize")
    assert body["text"] == "No activity has been recorded for this account."


def test_e4_account_6_spike_week_is_capped_at_five_locations(api: TestClient) -> None:
    configure(enabled=True)
    flagged, flagged_total, not_judged = counts(api, 6, "2026-06-01")
    assert flagged_total > 5
    body = post(api, {"week": "2026-06-01"}, account=6)
    lines = body["text"].splitlines()
    assert lines[0] == (
        "Week of 2026-06-01: 880 events, higher than usual (46.8 to 100.2) for this account."
    )
    assert [line.split(":")[0] for line in lines[1:6]] == [r["location"] for r in flagged[:5]]
    assert lines[6] == f"More flagged locations not listed: {flagged_total - 5}."
    assert len(lines) == 7 + (1 if not_judged else 0)
    assert body["headline"] == (
        "The whole account is higher than usual, across several locations. "
        f"Start with {flagged[0]['location']}."
    )


def test_e5_account_6_last_week_counts_the_too_quiet_location(api: TestClient) -> None:
    configure(enabled=True)
    flagged, flagged_total, not_judged = counts(api, 6, "2026-07-20")
    assert flagged_total == 0 and not_judged >= 1  # Site M, median 3.5 < 4 (T3 S11)
    lines = post(api, {"week": "2026-07-20"}, account=6)["text"].splitlines()
    assert lines[0].startswith("Week of 2026-07-20:")
    assert lines[1:] == [
        "No locations were flagged this week.",
        f"Locations that could not be judged: {not_judged}.",
    ]


def test_e6_a_week_with_no_flagged_location(api: TestClient) -> None:
    # Found at S3 from /api/report: account 15 at 2026-03-30 has no flagged or unjudged location.
    configure(enabled=True)
    flagged, flagged_total, not_judged = counts(api, 15, "2026-03-30")
    assert (flagged_total, not_judged) == (0, 0)
    body = post(api, {"week": "2026-03-30"})
    assert body["text"].splitlines()[1:] == ["No locations were flagged this week."]
    assert body["headline"] == "Nothing stands out this week."
