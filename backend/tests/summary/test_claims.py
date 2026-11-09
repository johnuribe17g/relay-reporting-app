"""Claim validation (plans/T5-ai-summary.md §2b, V1 to V10). Pure."""

import json
from typing import Any

import pytest

from app.summary.claims import ValidSummary, validate_summary
from app.summary.errors import InvalidSummary
from app.summary.facts import SummaryFacts, build_facts
from app.summary.render import fact_lines, template_lines
from tests.summary import builders as b

F1 = build_facts(b.f1())
F5 = build_facts(b.f5())
HEADLINE = "[L1] is higher than usual."
ACCOUNT = {"scope": "account", "location": None, "metric": "total", "verdict": "normal"}


def claim(location: str, verdict: str = "higher", metric: str = "total") -> dict[str, Any]:
    return {"scope": "location", "location": location, "metric": metric, "verdict": verdict}


def run(claims: list[Any], facts: SummaryFacts = F1, headline: Any = HEADLINE) -> ValidSummary:
    return validate_summary(json.dumps({"headline": headline, "claims": claims}), facts)


def rejected(claims: list[Any], facts: SummaryFacts = F1) -> None:
    with pytest.raises(InvalidSummary):
        run(claims, facts)


def test_v1_valid_claims_render_the_fact_lines_of_the_template() -> None:
    valid = run([ACCOUNT, claim("L1")])
    assert fact_lines(F1, valid.claims) == template_lines(F1)


def test_v2_claim_order_is_the_order_of_the_location_lines() -> None:
    claims = [ACCOUNT, claim("L2", "lower"), claim("L1")]
    lines = fact_lines(F5, run(claims, F5, "Start with [L2].").claims)
    assert [line.split(":")[0] for line in lines[1:3]] == ["Site D", "Site C"]
    assert lines[0].startswith("Week of 2026-07-20")


def test_v3_unlisted_id() -> None:
    rejected([ACCOUNT, claim("L1"), claim("L9")])


@pytest.mark.parametrize("bad", ["l1", "L1 ", "Site C"])
def test_v4_ids_only_exact_match(bad: str) -> None:
    rejected([ACCOUNT, claim(bad)])


def test_v5_verdict_must_match_the_payload() -> None:
    rejected([ACCOUNT, claim("L1", "lower")])
    rejected([{**ACCOUNT, "verdict": "higher"}, claim("L1")])


@pytest.mark.parametrize("metric", ["revenue", "call_received"])
def test_v6_only_total(metric: str) -> None:
    rejected([ACCOUNT, claim("L1", metric=metric)])


@pytest.mark.parametrize(
    "raw",
    [
        "not json {",
        '{"headline": "x", "claims": "x"}',
        "[]",
        "",
        None,
    ],
)
def test_v7_malformed_output(raw: Any) -> None:
    with pytest.raises(InvalidSummary):
        validate_summary(raw, F1)


def test_v8_extra_keys_are_rejected() -> None:
    rejected([ACCOUNT, {**claim("L1"), "total": 999}])
    rejected([ACCOUNT, {**claim("L1"), "text": "free text"}])
    extra_top = json.dumps({"headline": HEADLINE, "claims": [ACCOUNT, claim("L1")], "total": 1})
    with pytest.raises(InvalidSummary):
        validate_summary(extra_top, F1)


def test_v9_every_listed_location_needs_a_claim() -> None:
    rejected([ACCOUNT])


def test_v10_duplicates() -> None:
    rejected([ACCOUNT, claim("L1"), claim("L1")])
    rejected([ACCOUNT, ACCOUNT, claim("L1")])
