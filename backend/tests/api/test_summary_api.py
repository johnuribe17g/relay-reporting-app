"""POST /api/summary on tiny hand-computed data (plans/T5-ai-summary.md §2d).

Same fixture as `test_api_fixture.py` (baseline 4 weeks, min history 2, z_min 2, min_abs 3),
account 1 (Chicago) at its default week 2026-02-23. Hand arithmetic, with
spread = max(1.4826*MAD, sqrt(median), 1):
- Site A: history 5, 5, 5 (02-02, 02-09, 02-16), x = 6 + 3 + 2 = 11 (the unknown event is not
  counted). median 5, MAD 0, spread sqrt(5) = 2.2361, z = 6 / 2.2361 = 2.683, diff 6 >= 3: higher.
  h = max(2 * 2.2361, 3) = 4.4721, band 0.5279 to 9.4721 (shown 0.5 to 9.5).
- Account: history 5+6 = 11, 5+4 = 9, 5+6 = 11; x = 11 + 6 + 5 = 22. median 11, MAD 0, spread
  sqrt(11) = 3.3166, z = 11 / 3.3166 = 3.317, diff 11: higher. h = 6.6332, band 4.3668 to 17.6332
  (shown 4.4 to 17.6).
- Main St: 6, 4, 6, x = 6: normal. Late starts at 02-23: not enough history (1 location).
Each test runs on the rolled-back `conn`; no module here uses the seeded connection.
"""

import json
from typing import Any, Literal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.deps import get_summary_provider, get_summary_settings
from app.main import app
from app.settings import MockMode, SummarySettings
from app.summary.providers import MockProvider
from tests.api.conftest import ClientFactory, Events
from tests.api.test_api_fixture import BOUNDS, PARAMS, hdr, load_events

TEXT = "\n".join(
    [
        "Week of 2026-02-23: 22 events, higher than usual (4.4 to 17.6) for this account.",
        "Site A: 11 events, higher than usual (0.5 to 9.5); +6 against the usual 5.",
        "Locations that could not be judged: 1.",
    ]
)


@pytest.fixture
def api(conn: Connection, make_client: ClientFactory) -> TestClient:
    load_events(Events(conn))
    return make_client(conn, params=PARAMS, bounds=BOUNDS)


def configure(*, enabled: bool, mode: MockMode = "ok") -> None:
    settings = SummarySettings(llm_summary_enabled=enabled, summary_mock_mode=mode)
    app.dependency_overrides[get_summary_settings] = lambda: settings
    app.dependency_overrides[get_summary_provider] = lambda: MockProvider(mode)


def post(api: TestClient, body: dict[str, Any], account: int = 1) -> Any:
    return api.post("/api/summary", json=body, headers=hdr(account))


def test_a1_flag_off_is_the_template_for_the_default_week(api: TestClient) -> None:
    configure(enabled=False)
    response = post(api, {})
    assert response.status_code == 200
    body = response.json()
    assert (body["source"], body["reason"], body["provider"]) == ("template", "disabled", "mock")
    assert body["week"] == "2026-02-23" == api.get("/api/report", headers=hdr(1)).json()["week"]
    assert body["headline"] is None and body["text"] == TEXT
    assert body["prompt_version"] == "summary-v1"


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("week", ["2026-02-24", "abc"])
def test_a2_invalid_week_is_422_in_both_flag_states(
    api: TestClient, enabled: bool, week: str
) -> None:
    configure(enabled=enabled)
    response = post(api, {"week": week})
    assert response.status_code == 422
    assert response.json() == api.get(f"/api/report?week={week}", headers=hdr(1)).json()
    assert response.json()["error"]["code"] == "invalid_week"


def test_a4_unknown_account(api: TestClient) -> None:
    configure(enabled=True)
    response = post(api, {}, account=999)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "account_not_found"


class Recording:
    name: Literal["mock", "anthropic"] = "mock"

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.inner = MockProvider("ok")

    def complete(self, system: str, user: str) -> str:
        self.prompts.append(user)
        return self.inner.complete(system, user)


def payload_of(prompt: str) -> dict[str, Any]:
    start, end = prompt.index("<data>") + 6, prompt.index("</data>")
    return json.loads(prompt[start:end])  # type: ignore[no-any-return]


def test_a5_the_provider_sees_only_the_requesting_account(api: TestClient) -> None:
    recorder = Recording()
    app.dependency_overrides[get_summary_settings] = lambda: SummarySettings(
        llm_summary_enabled=True
    )
    app.dependency_overrides[get_summary_provider] = lambda: recorder
    one = post(api, {}, account=1).json()
    payload = payload_of(recorder.prompts[0])
    # 22 is account 1 alone; accounts 2 and 4 hold events in the same weeks (4 and 5 more).
    assert payload["account"]["total"] == 22
    assert [loc["id"] for loc in payload["locations"]] == ["L1"]
    assert "Bolt" not in one["text"] and "Newco" not in one["text"]
    post(api, {}, account=2)
    assert payload_of(recorder.prompts[1])["account"]["total"] == 4
    assert payload_of(recorder.prompts[1])["locations"] == []


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        ("exception", "provider_error"),
        ("timeout", "timeout"),
        ("unknown_location", "validation_failed"),
        ("contradicting_verdict", "validation_failed"),
        ("malformed_json", "validation_failed"),
    ],
)
def test_a7_each_failure_mode_is_a_200_template(
    api: TestClient, mode: MockMode, reason: str
) -> None:
    configure(enabled=True, mode=mode)
    response = post(api, {})
    assert response.status_code == 200
    body = response.json()
    assert (body["source"], body["reason"], body["headline"]) == ("template", reason, None)
    assert body["text"] == TEXT


def test_a8_flag_on_gives_a_headline_and_the_same_fact_lines(api: TestClient) -> None:
    configure(enabled=True)
    body = post(api, {}).json()
    assert (body["source"], body["reason"], body["provider"]) == ("ai", None, "mock")
    assert body["headline"] == "The account total is higher than usual. Start with Site A."
    assert body["text"] == TEXT
