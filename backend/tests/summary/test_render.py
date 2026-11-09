"""Fact lines and the template (plans/T5-ai-summary.md §2a, R1 to R11). Pure, no database."""

import json
from datetime import date

from app.domain.models import Verdict
from app.schemas import Report
from app.summary.facts import build_facts, prompt_payload
from app.summary.render import template_lines
from tests.summary import builders as b

F1_LINES = [
    "Week of 2026-07-20: 20 events, within the usual range (7.1 to 30.9) for this account.",
    "Site C: 12 events, higher than usual (0.8 to 10.2); +6.5 against the usual 5.5.",
]
NO_FLAGS = "No locations were flagged this week."


def lines(report: Report) -> list[str]:
    return template_lines(build_facts(report))


def test_r1_template_of_f1() -> None:
    assert lines(b.f1()) == F1_LINES


def test_r2_nothing_flagged() -> None:
    assert lines(b.f2()) == [F1_LINES[0], NO_FLAGS]


def test_r3_locations_that_could_not_be_judged() -> None:
    assert lines(b.f3()) == [F1_LINES[0], NO_FLAGS, "Locations that could not be judged: 3."]


def test_r4_cap_of_five_and_the_rest_counted() -> None:
    expected = [F1_LINES[0]] + [
        f"Loc{i}: {9 + i} events, higher than usual (0 to 8); +{4 + i} against the usual 5."
        for i in range(1, 6)
    ]
    assert lines(b.f4()) == [*expected, "More flagged locations not listed: 2."]
    assert expected[1] == "Loc1: 10 events, higher than usual (0 to 8); +5 against the usual 5."
    assert expected[5] == "Loc5: 14 events, higher than usual (0 to 8); +9 against the usual 5."


def test_r6_band_low_is_clipped_at_zero() -> None:
    row = b.location("X", Verdict.HIGHER, 8, 3.0, (-1.4304, 10.5), 5.0)
    text = "\n".join(lines(b.report(b.ACCOUNT_NORMAL, [row])))
    assert "(0 to 10.5)" in text
    assert "−1.4" not in text and "-1.4" not in text


def test_r7_negative_diff_uses_the_minus_sign() -> None:
    assert lines(b.f5())[2] == (
        "Site D: 2 events, lower than usual (3.5 to 10.5); −5 against the usual 7."
    )


def test_r8_week_null() -> None:
    assert lines(b.empty_report(Verdict.NO_ACTIVITY)) == [
        "No activity has been recorded for this account."
    ]
    assert lines(b.empty_report(Verdict.NOT_ENOUGH_HISTORY)) == [
        "No week can be judged yet for this account: not enough history."
    ]


def test_r9_account_not_judged() -> None:
    young = b.report(b.summary(Verdict.NOT_ENOUGH_HISTORY, 5, history_weeks=5), [])
    assert lines(young)[0] == "Week of 2026-07-20: not enough history to judge this account."
    quiet = b.report(b.summary(Verdict.TOO_QUIET, 3, 3.5, (0.0, 7.0)), [])
    assert lines(quiet)[0] == (
        "Week of 2026-07-20: this account is too quiet to judge (usual weekly total 3.5, below 4)."
    )


def test_r10_spike_week_line() -> None:
    spike = b.report(
        b.summary(Verdict.HIGHER, 880, 73.5, (46.8132, 100.1868)), [], week=date(2026, 6, 1)
    )
    assert lines(spike)[0] == (
        "Week of 2026-06-01: 880 events, higher than usual (46.8 to 100.2) for this account."
    )


def test_r11_the_payload_has_ids_and_no_names() -> None:
    facts = build_facts(b.f5())
    payload = json.dumps(prompt_payload(facts))
    for name in ("Site C", "Site D", "Site A", "Site B", b.ACCOUNT_NAME, "America/Chicago"):
        assert name not in payload
    assert [loc["id"] for loc in prompt_payload(facts)["locations"]] == ["L1", "L2"]
    assert dict(facts.names) == {"L1": "Site C", "L2": "Site D"}
