"""Headline validation and rendering (plans/T5-ai-summary.md §2b, H1 to H13). Pure."""

import json
from typing import Any

import pytest

from app.domain.models import Verdict
from app.summary.claims import validate_summary
from app.summary.errors import InvalidSummary
from app.summary.facts import SummaryFacts, build_facts
from tests.summary import builders as b

F5 = build_facts(b.f5())
CLAIMS: list[dict[str, Any]] = [
    {"scope": "account", "location": None, "metric": "total", "verdict": "normal"},
    {"scope": "location", "location": "L1", "metric": "total", "verdict": "higher"},
    {"scope": "location", "location": "L2", "metric": "total", "verdict": "lower"},
]


def accepted(headline: Any, facts: SummaryFacts = F5, claims: list[Any] | None = None) -> str:
    raw = json.dumps({"headline": headline, "claims": CLAIMS if claims is None else claims})
    return validate_summary(raw, facts).headline


def rejected(headline: Any, facts: SummaryFacts = F5, claims: list[Any] | None = None) -> None:
    with pytest.raises(InvalidSummary):
        accepted(headline, facts, claims)


def test_h1_each_cited_location_finds_its_own_direction_word() -> None:
    assert accepted("[L1] is higher than usual while [L2] is lower; look at [L1] first.") == (
        "Site C is higher than usual while Site D is lower; look at Site C first."
    )


def test_h2_length_boundary() -> None:
    assert accepted("a" * 200) == "a" * 200
    rejected("a" * 201)


@pytest.mark.parametrize("value", ["", "   ", None, 7, ["x"]])
def test_h3_required_string(value: Any) -> None:
    rejected(value)


def test_h3_missing_key() -> None:
    raw = json.dumps({"claims": CLAIMS})
    with pytest.raises(InvalidSummary):
        validate_summary(raw, F5)


@pytest.mark.parametrize("text", ["[L1] rose 12 percent.", "[L1] is up 3x.", "Es ist ٣ Uhr."])
def test_h4_digits_are_rejected(text: str) -> None:
    rejected(text)


def test_h5_the_digit_in_an_id_token_is_not_a_digit() -> None:
    assert accepted("[L1] is higher than usual.") == "Site C is higher than usual."


@pytest.mark.parametrize(
    "text", ["[L3] is higher.", "[L0] is higher.", "[Site C] is higher.", "[l1] is higher."]
)
def test_h6_tokens_must_be_listed_ids(text: str) -> None:
    rejected(text)


@pytest.mark.parametrize("text", ["[L1] is lower than usual.", "[L2] spiked.", "[L1] is down."])
def test_h7_direction_against_the_cited_location(text: str) -> None:
    rejected(text)


def test_h8_the_sentence_is_checked_per_location() -> None:
    rejected("[L1] is higher than usual. [L2] is higher too.")


def test_h9_a_sentence_without_tokens_or_direction_words_is_not_checked() -> None:
    assert accepted("Both look unusual. [L1] is higher.") == "Both look unusual. Site C is higher."


def test_h10_no_token() -> None:
    assert accepted("Nothing stands out this week.") == "Nothing stands out this week."


def test_h11_a_digit_in_the_substituted_name_is_fine() -> None:
    renamed = b.f1().model_copy(
        update={"locations": [b.location("Site 7", Verdict.HIGHER, 12, 5.5, (0.8, 10.2), 6.5)]}
    )
    facts = build_facts(renamed)
    assert accepted("Start with [L1].", facts, CLAIMS[:2]) == "Start with Site 7."


def test_h12_markup_is_kept_as_literal_text() -> None:
    assert accepted("<b>x</b> stands out.") == "<b>x</b> stands out."


def with_account(verdict: Verdict) -> SummaryFacts:
    return build_facts(b.with_account_verdict(b.f1(), verdict))


def account_claims(verdict: str) -> list[Any]:
    return [dict(CLAIMS[0], verdict=verdict), CLAIMS[1]]


def test_h13_tokenless_sentence_against_the_account_verdict() -> None:
    higher = with_account(Verdict.HIGHER)
    lower = with_account(Verdict.LOWER)
    normal = with_account(Verdict.NORMAL)
    rejected("The whole account is lower than usual.", higher, account_claims("higher"))
    rejected("The whole account is higher than usual.", lower, account_claims("lower"))
    text = "The whole account is higher than usual."
    assert accepted(text, higher, account_claims("higher")) == text
    # Known limit, pinned: with a normal account, direction words are not checked.
    wrong = "The whole account is lower than usual."
    assert accepted(wrong, normal, account_claims("normal")) == wrong


def test_h14_extended_lexicon() -> None:
    rejected("[L1] dropped sharply.")
    lower_c = b.f5().model_copy(
        update={
            "locations": [
                b.location("Site C", Verdict.LOWER, 2, 7.0, (3.5, 10.5), -5.0),
                b.SITE_D,
            ]
        }
    )
    claims = [CLAIMS[0], dict(CLAIMS[1], verdict="lower"), CLAIMS[2]]
    rejected("[L1] rose.", build_facts(lower_c), claims)
