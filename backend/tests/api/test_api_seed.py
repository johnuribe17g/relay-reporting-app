"""The real seed through the API (plans/T3-backend-api.md §2c).

Real params, real `get_bounds`, real `get_current_account`; only `get_conn` is overridden. Expected
values are the T2 anchors (arithmetic in plans/T2-backend-core.md §2g) or were computed by hand from
the series read with the queries in the T3 plan's Appendix; they are not taken from the code.
"""

import math
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.domain.ranking import rank
from app.domain.verdict import judge
from app.series import fetch_series, history_and_x
from app.settings import ReportSettings, settings
from tests.api.conftest import ClientFactory

FIRST = date(2026, 2, 2)
PARAMS = ReportSettings().judge_params()
ACCOUNTS_WITH_EVENTS = [i for i in range(1, 20)]


@pytest.fixture
def api(seeded_conn: Connection, make_client: ClientFactory) -> TestClient:
    return make_client(seeded_conn)


def hdr(account: int) -> dict[str, str]:
    return {"X-Account-Id": str(account)}


def by_name(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["location"]: row for row in rows}


def test_s1_accounts(api: TestClient) -> None:
    rows = api.get("/api/accounts").json()
    assert [r["id"] for r in rows] == list(range(1, 21))
    by_id = {r["id"]: r for r in rows}
    assert by_id[6] == {"id": 6, "name": "Metro Collision Centers", "timezone": "America/New_York"}
    assert by_id[20] == {"id": 20, "name": "Quiet Harbor Spa", "timezone": "America/Los_Angeles"}


def test_s2_weeks_for_account_1(api: TestClient) -> None:
    body = api.get("/api/weeks", headers=hdr(1)).json()
    # first = 2026-02-02 + 8 * 7 days = 2026-03-30; 03-30 .. 07-20 is 16 steps = 17 weeks
    assert len(body["weeks"]) == 17
    assert body["weeks"][0] == "2026-03-30"
    assert body["weeks"][-1] == "2026-07-20"
    assert body["default_week"] == "2026-07-20"
    assert body["as_of"] == "2026-07-27T22:20:34Z"


@pytest.mark.parametrize("account", ACCOUNTS_WITH_EVENTS)
def test_s3_every_account_has_the_same_weeks_in_its_own_timezone(
    api: TestClient, account: int
) -> None:
    body = api.get("/api/weeks", headers=hdr(account)).json()
    assert len(body["weeks"]) == 17
    assert (body["weeks"][0], body["default_week"]) == ("2026-03-30", "2026-07-20")


def test_s4_account_20_has_no_week(api: TestClient) -> None:
    body = api.get("/api/weeks", headers=hdr(20)).json()
    assert (body["weeks"], body["default_week"]) == ([], None)


@pytest.fixture
def default_report(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(settings, "demo_account_id", 15)
    response = api.get("/api/report")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_s5_default_account_and_week(default_report: dict[str, Any]) -> None:
    assert default_report["account"]["id"] == 15
    assert default_report["week"] == "2026-07-20"
    s = default_report["account_summary"]
    # history 15,16,25,23,15,33,23,14,24,16,19,19, x 20: median 19, MAD 4, spread 1.4826*4
    spread = 1.4826 * 4
    assert s["total"] == 20
    assert s["verdict"] == "normal"
    assert s["baseline"]["median"] == 19.0
    assert s["baseline"]["mad"] == 4.0
    assert s["baseline"]["spread"] == pytest.approx(spread)
    assert s["z"] == pytest.approx(1 / spread)  # 0.1686


def test_s6_default_account_locations_in_rank_order(default_report: dict[str, Any]) -> None:
    rows = default_report["locations"]
    assert [r["location"] for r in rows] == ["Site C", "Site B", "Site A"]
    by = by_name(rows)
    # Site C: median 5.5, MAD 1.0, spread sqrt(5.5), x 12
    r55 = math.sqrt(5.5)
    c = by["Site C"]
    assert (c["total"], c["verdict"]) == (12, "higher")
    assert c["baseline"]["median"] == 5.5
    assert c["baseline"]["mad"] == 1.0
    assert c["z"] == pytest.approx(6.5 / r55)  # 2.7716
    assert c["baseline"]["band_low"] == pytest.approx(5.5 - 2 * r55)  # 0.8096
    assert c["baseline"]["band_high"] == pytest.approx(5.5 + 2 * r55)  # 10.1904
    # Site B: median 6.5, MAD 2.5, spread 1.4826*2.5, x 2: z -1.2141 (|d| 4.5 >= 3, |z| < 2)
    b = by["Site B"]
    assert (b["total"], b["verdict"]) == (2, "normal")
    assert b["baseline"]["median"] == 6.5
    assert b["baseline"]["mad"] == 2.5
    assert b["z"] == pytest.approx(-4.5 / (1.4826 * 2.5))
    # Site A: median 7, MAD 1.5, spread sqrt(7) (above 1.4826*1.5), x 6: z -0.3780
    a = by["Site A"]
    assert (a["total"], a["verdict"]) == (6, "normal")
    assert a["baseline"]["median"] == 7.0
    assert a["z"] == pytest.approx(-1 / math.sqrt(7))


def test_s7_account_6_spike_week_is_higher(api: TestClient) -> None:
    """Anchor A1 through the API."""
    body = api.get("/api/report", params={"week": "2026-06-01"}, headers=hdr(6)).json()
    s = body["account_summary"]
    spread = 1.4826 * 9
    assert (s["total"], s["verdict"], s["history_weeks"]) == (880, "higher", 12)
    assert s["baseline"]["median"] == 73.5
    assert s["baseline"]["mad"] == 9.0
    assert s["baseline"]["weeks_used"] == 12
    assert s["z"] == pytest.approx(806.5 / spread)  # 60.44
    assert s["diff"] == pytest.approx(806.5)


def test_s8_ordinary_location_matches_anchor_a2(api: TestClient) -> None:
    body = api.get(
        "/api/locations/Site%20A/history", params={"week": "2026-07-20"}, headers=hdr(1)
    ).json()
    weeks = body["weeks"]
    assert len(weeks) == 13
    assert [w["total"] for w in weeks] == [8, 7, 6, 6, 5, 7, 9, 11, 7, 10, 7, 9, 9]
    assert (weeks[0]["week"], weeks[-2]["week"], weeks[-1]["week"]) == (
        "2026-04-27",
        "2026-07-13",
        "2026-07-20",
    )
    assert weeks[-1]["role"] == "selected"
    assert all(w["role"] == "baseline" for w in weeks[:-1])
    r7 = math.sqrt(7)
    assert body["verdict"] == "normal"
    assert body["z"] == pytest.approx(2 / r7)  # 0.7559
    assert body["baseline"]["median"] == 7.0
    assert body["baseline"]["mad"] == 1.0
    assert body["baseline"]["band_low"] == pytest.approx(7 - 2 * r7)  # 1.7085
    assert body["baseline"]["band_high"] == pytest.approx(7 + 2 * r7)  # 12.2915
    # the same numbers in /api/report
    report = api.get("/api/report", headers=hdr(1)).json()
    row = by_name(report["locations"])["Site A"]
    assert row["total"] == 9
    assert row["z"] == pytest.approx(body["z"])
    assert row["baseline"] == body["baseline"]


def test_s9_zero_week_inside_the_baseline_is_an_explicit_row(api: TestClient) -> None:
    """Anchor A9: account 6 Site G, history includes 0 at 2026-06-29."""
    body = api.get(
        "/api/locations/Site%20G/history", params={"week": "2026-07-20"}, headers=hdr(6)
    ).json()
    by_week = {w["week"]: w["total"] for w in body["weeks"]}
    assert by_week["2026-06-29"] == 0
    assert by_week["2026-06-01"] == 57
    assert [w["total"] for w in body["weeks"]][:-1] == [6, 4, 3, 7, 5, 57, 4, 5, 3, 0, 4, 6]
    assert body["weeks"][-1]["total"] == 6
    assert body["verdict"] == "normal"
    assert body["baseline"]["median"] == 4.5
    assert body["baseline"]["mad"] == 1.5
    assert body["z"] == pytest.approx(1.5 / (1.4826 * 1.5))  # 0.6745


def test_s10_account_20_report_is_an_empty_state(api: TestClient) -> None:
    response = api.get("/api/report", headers=hdr(20))
    assert response.status_code == 200
    body = response.json()
    assert body["week"] is None
    assert body["account_summary"]["verdict"] == "no_activity"
    assert body["locations"] == []


@pytest.mark.parametrize(
    ("account", "location", "median"), [(6, "Site M", 3.5), (18, "Site A", 3.0)]
)
def test_s11_too_quiet_locations_come_last_without_a_z(
    api: TestClient, account: int, location: str, median: float
) -> None:
    rows = api.get("/api/report", headers=hdr(account)).json()["locations"]
    row = by_name(rows)[location]
    assert row["verdict"] == "too_quiet"
    assert row["z"] is None and row["diff"] is None
    assert row["baseline"]["median"] == median
    assert rows[-1]["location"] == location  # the only unjudged location of the account
    assert all(r["z"] is not None for r in rows[:-1])


@pytest.mark.parametrize(
    ("account", "week"), [(6, "2026-06-01"), (6, "2026-07-20"), (12, "2026-07-20")]
)
def test_s12_ranking_order(
    api: TestClient, seeded_conn: Connection, account: int, week: str
) -> None:
    rows = api.get("/api/report", params={"week": week}, headers=hdr(account)).json()["locations"]
    names = [r["location"] for r in rows]
    # independent invariant: judged first by |z| non-increasing, then unjudged by name
    judged = [r for r in rows if r["z"] is not None]
    unjudged = [r for r in rows if r["z"] is None]
    assert rows == judged + unjudged
    zs = [abs(r["z"]) for r in judged]
    assert zs == sorted(zs, reverse=True)
    assert [r["location"] for r in unjudged] == sorted(r["location"] for r in unjudged)
    # and the same order as rank() over judge() computed here from the series
    result = fetch_series(seeded_conn, account, date.fromisoformat(week), FIRST, 12)
    expected = rank(
        [(s.key, judge(*history_and_x(s), PARAMS)) for s in result.locations if s.key is not None]
    )
    assert names == [name for name, _ in expected]


@pytest.mark.parametrize("account", ACCOUNTS_WITH_EVENTS)
def test_s13_no_unknown_event_types_in_the_seed(api: TestClient, account: int) -> None:
    body = api.get("/api/report", headers=hdr(account)).json()
    assert body["account_summary"]["data_quality"] == {"unknown_events_in_window": 0}
    assert all(row["data_quality"] == {"unknown_events_in_window": 0} for row in body["locations"])


def test_s15_reviewer_case_zero_week_in_baseline_and_diff_on_the_min_abs_boundary(
    api: TestClient,
) -> None:
    """Reviewer-sourced (T3 aggregation-reviewer): account 6 Site N, week 2026-04-27.

    History 02-02 .. 04-20: 6,4,8,0,8,8,5,6,3,8,1,8 (the 0 is 02-23), x = 3.
    Sorted 0,1,3,4,5,6,6,8,8,8,8,8 -> median (6+6)/2 = 6.
    |dev| 0,2,2,6,2,2,1,0,3,2,5,2 -> sorted 0,0,1,2,2,2,2,2,2,3,5,6 -> MAD (2+2)/2 = 2.
    spread = max(1.4826*2 = 2.9652, sqrt(6) = 2.449, 1) = 2.9652;
    diff = 3 - 6 = -3 (|diff| = min_abs), z = -3/2.9652 = -1.0117 (|z| < 2) -> normal.
    Band: h = max(2*2.9652, 3) = 5.9304 -> (0.0696, 11.9304).
    """
    body = api.get(
        "/api/locations/Site%20N/history", params={"week": "2026-04-27"}, headers=hdr(6)
    ).json()
    totals = [w["total"] for w in body["weeks"]]
    assert totals == [6, 4, 8, 0, 8, 8, 5, 6, 3, 8, 1, 8, 3]
    assert body["weeks"][0]["week"] == "2026-02-02"
    assert body["weeks"][3]["week"] == "2026-02-23"
    spread = 1.4826 * 2
    assert body["verdict"] == "normal"
    assert body["baseline"]["median"] == 6.0
    assert body["baseline"]["mad"] == 2.0
    assert body["baseline"]["spread"] == pytest.approx(spread)
    assert body["diff"] == -3.0
    assert body["z"] == pytest.approx(-3 / spread)  # -1.0117
    assert body["baseline"]["band_low"] == pytest.approx(6 - 2 * spread)  # 0.0696
    assert body["baseline"]["band_high"] == pytest.approx(6 + 2 * spread)  # 11.9304


def test_s16_reviewer_case_location_in_the_spike_week_with_a_zero_week_in_the_baseline(
    api: TestClient,
) -> None:
    """Reviewer-sourced (T3 aggregation-reviewer): account 6 Site G, week 2026-06-01.

    History 03-09 .. 05-25: 3,5,7,8,2,0,2,6,4,3,7,5 (the 0 is 04-13), x = 57.
    Sorted 0,2,2,3,3,4,5,5,6,7,7,8 -> median (4+5)/2 = 4.5.
    |dev| 1.5,.5,2.5,3.5,2.5,4.5,2.5,1.5,.5,1.5,2.5,.5
    -> sorted .5,.5,.5,1.5,1.5,1.5,2.5,2.5,2.5,2.5,3.5,4.5
    -> MAD (1.5+2.5)/2 = 2.
    spread = max(2.9652, sqrt(4.5) = 2.121, 1) = 2.9652; diff = 52.5,
    z = 52.5/2.9652 = 17.7054 -> higher.
    Band: h = 5.9304 -> band_low = 4.5 - 5.9304 = -1.4304 (not clipped at 0).
    """
    body = api.get(
        "/api/locations/Site%20G/history", params={"week": "2026-06-01"}, headers=hdr(6)
    ).json()
    totals = [w["total"] for w in body["weeks"]]
    assert totals == [3, 5, 7, 8, 2, 0, 2, 6, 4, 3, 7, 5, 57]
    assert body["weeks"][5]["week"] == "2026-04-13"
    spread = 1.4826 * 2
    assert body["verdict"] == "higher"
    assert body["baseline"]["median"] == 4.5
    assert body["baseline"]["mad"] == 2.0
    assert body["diff"] == 52.5
    assert body["z"] == pytest.approx(52.5 / spread)  # 17.7054
    assert body["baseline"]["band_low"] == pytest.approx(4.5 - 2 * spread)  # -1.4304
    assert body["baseline"]["band_high"] == pytest.approx(4.5 + 2 * spread)  # 10.4304
