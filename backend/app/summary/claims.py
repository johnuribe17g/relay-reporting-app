"""Parsing and validating what the model returned (plans/T5-ai-summary.md §1b).

Everything is a near-enum: a claim cites a listed id, a known metric and the payload's verdict.
"""

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError

from app.domain.models import Verdict
from app.summary.errors import InvalidSummary
from app.summary.facts import SummaryFacts
from app.summary.headline import render_headline, validate_headline

METRICS = frozenset({"total"})


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: Literal["account", "location"]
    location: StrictStr | None
    metric: Literal["total"]
    verdict: Verdict


class ModelSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: StrictStr
    claims: list[Claim]


@dataclass(frozen=True)
class ValidSummary:
    headline: str  # already rendered: id tokens replaced by names
    claims: tuple[Claim, ...]


def parse_summary(raw: object) -> ModelSummary:
    if not isinstance(raw, str):
        raise InvalidSummary("the provider did not return text")
    try:
        return ModelSummary.model_validate(json.loads(raw))
    except (ValueError, ValidationError) as exc:
        raise InvalidSummary("the output is not the expected JSON") from exc


def validate_claims(claims: list[Claim], facts: SummaryFacts) -> None:
    accounts = [c for c in claims if c.scope == "account"]
    if len(accounts) != 1 or accounts[0].location is not None:
        raise InvalidSummary("exactly one account claim, without a location, is required")
    if accounts[0].verdict != facts.account.verdict:
        raise InvalidSummary("the account verdict does not match")
    cited: list[str] = []
    for claim in claims:
        if claim.scope == "account":
            continue
        if claim.location is None or claim.location not in facts.ids:
            raise InvalidSummary(f"unknown location {claim.location!r}")
        if claim.verdict != facts.location(claim.location).verdict:
            raise InvalidSummary(f"the verdict of {claim.location} does not match")
        cited.append(claim.location)
    if len(set(cited)) != len(cited):
        raise InvalidSummary("duplicate location claim")
    if set(cited) != facts.ids:
        raise InvalidSummary("every listed location needs a claim")


def validate_summary(raw: object, facts: SummaryFacts) -> ValidSummary:
    summary = parse_summary(raw)
    validate_claims(summary.claims, facts)
    validate_headline(summary.headline, facts)
    return ValidSummary(
        headline=render_headline(summary.headline, facts), claims=tuple(summary.claims)
    )
