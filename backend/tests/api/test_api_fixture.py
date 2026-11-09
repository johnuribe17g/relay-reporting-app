"""API contract tests on tiny hand-computed data (plans/T3-backend-api.md §2b).

Params override: baseline 4 weeks, min history 2, z_min 2.0, min_abs 3.0, min_baseline_median 4.0.
Bounds override: data_start 2026-02-02 06:00:00, as_of 2026-03-02 06:30:00 (naive UTC).
February to 03-07 is CST (-6) / MST (-7). Chicago: 06:30 UTC is Mon 03-02 00:30, so the last
complete week is 02-23. Denver: 06:30 - 7 h is Sun 03-01 23:30, so it is 02-16.
Each test runs on the rolled-back `conn`; no module here uses the seeded connection.
"""

import math
from datetime import date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.deps import Bounds
from app.domain.models import JudgeParams
from app.settings import settings
from tests.api.conftest import ClientFactory, Events

PARAMS = JudgeParams(
    baseline_weeks=4, min_history_weeks=2, z_min=2.0, min_abs=3.0, min_baseline_median=4.0
)
BOUNDS = Bounds(data_start=datetime(2026, 2, 2, 6, 0, 0), as_of=datetime(2026, 3, 2, 6, 30, 0))
W0202, W0209, W0216, W0223 = (date(2026, 2, d) for d in (2, 9, 16, 23))


def hdr(account: int) -> dict[str, str]:
    return {"X-Account-Id": str(account)}


def load_accounts(ev: Events) -> None:
    ev.account(1, "Acme", "America/Chicago")
    ev.account(2, "Bolt", "America/Denver")
    ev.account(3, "Empty", "America/Chicago")
    ev.account(4, "Newco", "America/Chicago")


def load_events(ev: Events) -> None:
    load_accounts(ev)
    for week, n in ((W0202, 5), (W0209, 5), (W0216, 5)):
        ev.add(1, "Site A", week, calls=n)
    ev.add(1, "Site A", W0223, calls=6, leads=3, appointments=2, unknown=1)
    for week, n in ((W0202, 6), (W0209, 4), (W0216, 6), (W0223, 6)):
        ev.add(1, "Main St", week, calls=n)
    ev.add(1, "Late", W0223, calls=5)
    for week in (W0202, W0209, W0216, W0223):
        ev.add(2, "Site A", week, calls=4)
    ev.add(4, "Site A", W0223, calls=5)


@pytest.fixture
def api(conn: Connection, make_client: ClientFactory) -> TestClient:
    load_events(Events(conn))
    return make_client(conn, params=PARAMS, bounds=BOUNDS)


def by_name(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["location"]: row for row in rows}


# ---- weeks and accounts -------------------------------------------------------------------


def test_w1_weeks_for_chicago(api: TestClient) -> None:
    body = api.get("/api/weeks", headers=hdr(1)).json()
    assert body["account"] == {"id": 1, "name": "Acme", "timezone": "America/Chicago"}
    assert body["weeks"] == ["2026-02-16", "2026-02-23"]
    assert body["default_week"] == "2026-02-23"
    assert body["as_of"] == "2026-03-02T06:30:00Z"


def test_w2_weeks_for_denver_use_the_account_timezone(api: TestClient) -> None:
    body = api.get("/api/weeks", headers=hdr(2)).json()
    assert body["weeks"] == ["2026-02-16"]
    assert body["default_week"] == "2026-02-16"


def test_w3_account_without_events_has_no_week(api: TestClient) -> None:
    body = api.get("/api/weeks", headers=hdr(3)).json()
    assert body["weeks"] == []
    assert body["default_week"] is None


def test_w4_account_starting_after_the_range_has_no_week(api: TestClient) -> None:
    body = api.get("/api/weeks", headers=hdr(4)).json()
    assert body["weeks"] == []
    assert body["default_week"] is None


def test_w5_no_header_uses_the_demo_account(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "demo_account_id", 1)
    assert api.get("/api/weeks").json() == api.get("/api/weeks", headers=hdr(1)).json()


def test_w6_unknown_demo_account_is_404(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "demo_account_id", 999)
    response = api.get("/api/weeks")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "account_not_found"


def test_w7_accounts_are_listed_by_id(api: TestClient) -> None:
    assert api.get("/api/accounts").json() == [
        {"id": 1, "name": "Acme", "timezone": "America/Chicago"},
        {"id": 2, "name": "Bolt", "timezone": "America/Denver"},
        {"id": 3, "name": "Empty", "timezone": "America/Chicago"},
        {"id": 4, "name": "Newco", "timezone": "America/Chicago"},
    ]


def test_w8_no_events_anywhere_leaves_the_bounds_empty(
    conn: Connection, make_client: ClientFactory
) -> None:
    load_accounts(Events(conn))
    client = make_client(conn)  # real get_bounds: (None, None) on an empty view
    weeks = client.get("/api/weeks", headers=hdr(3)).json()
    assert (weeks["weeks"], weeks["default_week"], weeks["as_of"]) == ([], None, None)
    report = client.get("/api/report", headers=hdr(3))
    assert report.status_code == 200
    assert report.json()["account_summary"]["verdict"] == "no_activity"
    assert report.json()["as_of"] is None


# ---- report -------------------------------------------------------------------------------


def test_r1_default_week_account_summary(api: TestClient) -> None:
    body = api.get("/api/report", headers=hdr(1)).json()
    assert body["week"] == "2026-02-23"
    s = body["account_summary"]
    # history [11, 9, 11], x 22: median 11, MAD 0, spread = z = sqrt(11), band 11 +- 2*sqrt(11)
    r11 = math.sqrt(11)
    assert s["total"] == 22
    assert s["verdict"] == "higher"
    assert s["z"] == pytest.approx(r11)
    assert s["diff"] == pytest.approx(11.0)
    assert s["history_weeks"] == 3
    assert s["baseline"] == pytest.approx(
        {
            "median": 11.0,
            "mad": 0.0,
            "spread": r11,
            "weeks_used": 3,
            "band_low": 11 - 2 * r11,
            "band_high": 11 + 2 * r11,
        }
    )
    assert s["by_type"] == {"call_received": 17, "lead_created": 3, "appointment_set": 2}
    assert s["data_quality"] == {"unknown_events_in_window": 1}


def test_r2_locations_are_ranked_and_unjudged_come_last(api: TestClient) -> None:
    body = api.get("/api/report", headers=hdr(1)).json()
    assert [row["location"] for row in body["locations"]] == ["Site A", "Main St", "Late"]
    rows = by_name(body["locations"])
    r5, r6 = math.sqrt(5), math.sqrt(6)
    site_a = rows["Site A"]
    assert site_a["total"] == 11
    assert site_a["verdict"] == "higher"
    assert site_a["z"] == pytest.approx(6 / r5)
    assert site_a["baseline"]["band_low"] == pytest.approx(5 - 2 * r5)
    assert site_a["baseline"]["band_high"] == pytest.approx(5 + 2 * r5)
    assert site_a["by_type"] == {"call_received": 6, "lead_created": 3, "appointment_set": 2}
    assert site_a["data_quality"] == {"unknown_events_in_window": 1}
    main = rows["Main St"]
    assert (main["total"], main["verdict"], main["z"]) == (6, "normal", 0.0)
    assert main["baseline"]["median"] == 6.0
    assert main["baseline"]["spread"] == pytest.approx(r6)
    late = rows["Late"]
    assert late["total"] == 5
    assert late["verdict"] == "not_enough_history"
    assert late["history_weeks"] == 0
    assert late["z"] is None and late["baseline"] is None and late["diff"] is None


def test_r3_explicit_week_changes_the_verdicts_and_the_order(api: TestClient) -> None:
    body = api.get("/api/report", params={"week": "2026-02-16"}, headers=hdr(1)).json()
    assert body["week"] == "2026-02-16"
    s = body["account_summary"]
    r10 = math.sqrt(10)
    assert (s["total"], s["verdict"]) == (11, "normal")
    assert s["z"] == pytest.approx(1 / r10)
    assert s["baseline"]["median"] == 10.0
    assert s["baseline"]["mad"] == 1.0
    assert s["baseline"]["band_low"] == pytest.approx(10 - 2 * r10)
    assert s["baseline"]["band_high"] == pytest.approx(10 + 2 * r10)
    # Late starts 02-23, after this week: absent. |z| 0.4472 (Main St) before 0 (Site A).
    assert [row["location"] for row in body["locations"]] == ["Main St", "Site A"]
    rows = by_name(body["locations"])
    assert rows["Main St"]["z"] == pytest.approx(1 / math.sqrt(5))
    assert rows["Main St"]["baseline"]["median"] == 5.0
    assert rows["Site A"]["z"] == 0.0


def test_r4_parameters_and_as_of_are_echoed(api: TestClient) -> None:
    body = api.get("/api/report", headers=hdr(1)).json()
    assert body["parameters"] == {
        "baseline_weeks": 4,
        "min_history_weeks": 2,
        "z_min": 2.0,
        "min_abs": 3.0,
        "min_baseline_median": 4.0,
    }
    assert body["as_of"] == "2026-03-02T06:30:00Z"


def test_r5_other_accounts_and_later_weeks_do_not_leak(api: TestClient) -> None:
    body = api.get("/api/report", headers=hdr(2)).json()
    assert body["week"] == "2026-02-16"
    assert body["account_summary"]["total"] == 4
    assert body["account_summary"]["verdict"] == "normal"
    assert [row["location"] for row in body["locations"]] == ["Site A"]
    site_a = body["locations"][0]
    assert (site_a["total"], site_a["z"]) == (4, 0.0)
    assert site_a["baseline"]["median"] == 4.0
    assert site_a["baseline"]["spread"] == pytest.approx(2.0)


def test_r6_account_without_events_is_a_200_empty_state(api: TestClient) -> None:
    response = api.get("/api/report", headers=hdr(3))
    assert response.status_code == 200
    body = response.json()
    assert body["week"] is None
    assert body["locations"] == []
    s = body["account_summary"]
    assert s["verdict"] == "no_activity"
    assert s["total"] is None and s["baseline"] is None and s["by_type"] is None
    assert body["parameters"]["baseline_weeks"] == 4


def test_r7_account_without_a_judgeable_week(api: TestClient) -> None:
    response = api.get("/api/report", headers=hdr(4))
    assert response.status_code == 200
    body = response.json()
    assert body["week"] is None
    assert body["account_summary"]["verdict"] == "not_enough_history"
    assert body["locations"] == []


# ---- location history ---------------------------------------------------------------------


def test_h1_history_of_a_location_with_a_space_in_its_name(api: TestClient) -> None:
    response = api.get("/api/locations/Site%20A/history", headers=hdr(1))
    assert response.status_code == 200
    body = response.json()
    assert body["location"] == "Site A"
    assert body["week"] == "2026-02-23"
    assert [(w["week"], w["total"], w["role"]) for w in body["weeks"]] == [
        ("2026-02-02", 5, "baseline"),
        ("2026-02-09", 5, "baseline"),
        ("2026-02-16", 5, "baseline"),
        ("2026-02-23", 11, "selected"),
    ]
    assert body["weeks"][-1]["by_type"] == {
        "call_received": 6,
        "lead_created": 3,
        "appointment_set": 2,
    }
    r5 = math.sqrt(5)
    assert body["verdict"] == "higher"
    assert body["z"] == pytest.approx(6 / r5)
    assert body["baseline"]["median"] == 5.0
    assert body["baseline"]["band_low"] == pytest.approx(5 - 2 * r5)
    assert body["baseline"]["band_high"] == pytest.approx(5 + 2 * r5)
    assert body["data_quality"] == {"unknown_events_in_window": 1}
    assert body["parameters"]["z_min"] == 2.0
    assert body["as_of"] == "2026-03-02T06:30:00Z"


def test_h2_history_of_another_location(api: TestClient) -> None:
    body = api.get("/api/locations/Main%20St/history", headers=hdr(1)).json()
    assert [w["total"] for w in body["weeks"]] == [6, 4, 6, 6]
    assert (body["verdict"], body["z"]) == ("normal", 0.0)


def test_h3_location_with_no_history_is_not_judged(api: TestClient) -> None:
    response = api.get("/api/locations/Late/history", headers=hdr(1))
    assert response.status_code == 200
    body = response.json()
    assert [(w["week"], w["total"], w["role"]) for w in body["weeks"]] == [
        ("2026-02-23", 5, "selected")
    ]
    assert body["verdict"] == "not_enough_history"
    assert body["baseline"] is None and body["z"] is None


def test_h4_location_starting_after_the_week_is_404(api: TestClient) -> None:
    response = api.get("/api/locations/Late/history", params={"week": "2026-02-16"}, headers=hdr(1))
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "location_not_found"
    assert "2026-02-16" in error["message"]


@pytest.mark.parametrize(("path", "account"), [("Nope", 1), ("Main%20St", 2)])
def test_h5_unknown_location_or_other_accounts_location_is_404(
    api: TestClient, path: str, account: int
) -> None:
    response = api.get(f"/api/locations/{path}/history", headers=hdr(account))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "location_not_found"


def test_h6_location_name_is_matched_exactly(api: TestClient) -> None:
    response = api.get("/api/locations/site%20a/history", headers=hdr(1))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "location_not_found"


def test_h7_no_selectable_week_and_no_week_given_is_404(api: TestClient) -> None:
    response = api.get("/api/locations/Site%20A/history", headers=hdr(3))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "location_not_found"


def test_h8_week_is_checked_before_the_location(api: TestClient) -> None:
    response = api.get(
        "/api/locations/Site%20A/history", params={"week": "2026-02-09"}, headers=hdr(1)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_week"


# ---- errors -------------------------------------------------------------------------------


def test_e1_non_monday_week(api: TestClient) -> None:
    response = api.get("/api/report", params={"week": "2026-02-17"}, headers=hdr(1))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_week"
    assert "2026-02-16 .. 2026-02-23" in error["message"]


@pytest.mark.parametrize("week", ["2026-02-09", "2026-03-02"])
def test_e2_week_outside_the_range(api: TestClient, week: str) -> None:
    response = api.get("/api/report", params={"week": week}, headers=hdr(1))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_week"


@pytest.mark.parametrize("week", ["abc", "2026-13-01"])
def test_e3_week_that_is_not_a_date(api: TestClient, week: str) -> None:
    response = api.get("/api/report", params={"week": week}, headers=hdr(1))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_week"


def test_e4_explicit_week_for_an_account_without_a_selectable_week(api: TestClient) -> None:
    response = api.get("/api/report", params={"week": "2026-02-16"}, headers=hdr(3))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_week"
    assert "no selectable weeks" in error["message"]


@pytest.mark.parametrize(
    ("header", "status", "code"),
    [
        ("abc", 422, "invalid_request"),
        ("0", 422, "invalid_request"),
        ("999", 404, "account_not_found"),
    ],
)
def test_e5_bad_account_header(api: TestClient, header: str, status: int, code: str) -> None:
    response = api.get("/api/report", headers={"X-Account-Id": header})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_e6_unknown_route(api: TestClient) -> None:
    response = api.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    ("path", "query", "account"),
    [
        ("/api/report", {"week": "2026-02-17"}, "1"),
        ("/api/report", {"week": "abc"}, "1"),
        ("/api/report", {}, "abc"),
        ("/api/report", {}, "999"),
        ("/api/weeks", {}, "999"),
        ("/api/locations/Nope/history", {}, "1"),
        ("/api/locations/Site%20A/history", {"week": "2026-02-09"}, "1"),
        ("/api/nope", {}, "1"),
    ],
)
def test_e7_every_error_has_the_one_shape(
    api: TestClient, path: str, query: dict[str, str], account: str
) -> None:
    response = api.get(path, params=query, headers={"X-Account-Id": account})
    assert response.status_code >= 400
    body = response.json()
    assert list(body) == ["error"]
    assert sorted(body["error"]) == ["code", "message"]
    assert all(isinstance(v, str) and v for v in body["error"].values())
