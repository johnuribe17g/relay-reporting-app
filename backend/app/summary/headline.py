"""The model-written headline: validation and rendering (plans/T5-ai-summary.md §1b).

The model writes no number and no name. A location is an id token `[L1]`..`[L5]`; the server
substitutes the name. The direction check is a heuristic (D-29): the real guarantee is that every
figure comes from the server.
"""

import re

from app.domain.models import Verdict
from app.summary.errors import InvalidSummary
from app.summary.facts import SummaryFacts

MAX_HEADLINE_CHARS = 200

_BRACKET = re.compile(r"\[[^\]]*\]")
_TOKEN = re.compile(r"\[(L\d+)\]")
_SENTENCE_END = re.compile(r"[.!?]+")
_UP = re.compile(
    r"\b(higher|up|above|spike|spikes|spiked|rose|rise|rising|increase|increased"
    r"|jump|jumped|surge|surged|busier)\b",
    re.IGNORECASE,
)
_DOWN = re.compile(
    r"\b(lower|down|below|drop|dropped|fell|fall|falling|decrease|decreased"
    r"|decline|declined|dip|dipped|quieter)\b",
    re.IGNORECASE,
)


def _contradicts(verdict: Verdict, has_up: bool, has_down: bool) -> bool:
    """Only opposite-direction words and none of the matching direction."""
    if verdict == Verdict.HIGHER:
        return has_down and not has_up
    if verdict == Verdict.LOWER:
        return has_up and not has_down
    return False


def validate_headline(text: str, facts: SummaryFacts) -> None:
    """Raise `InvalidSummary` unless every headline rule holds."""
    if not text.strip():
        raise InvalidSummary("empty headline")
    if len(text) > MAX_HEADLINE_CHARS:
        raise InvalidSummary("headline too long")
    ids = facts.ids
    for bracket in _BRACKET.findall(text):
        if bracket[1:-1] not in ids:
            raise InvalidSummary(f"unknown location token {bracket!r}")
    if re.search(r"\d", _BRACKET.sub("", text)):
        raise InvalidSummary("headline contains a digit")
    for sentence in _SENTENCE_END.split(text):
        has_up = bool(_UP.search(sentence))
        has_down = bool(_DOWN.search(sentence))
        cited = _TOKEN.findall(sentence)
        if cited:
            for location_id in cited:
                if _contradicts(facts.location(location_id).verdict, has_up, has_down):
                    raise InvalidSummary(f"wording contradicts the verdict of {location_id}")
        elif _contradicts(facts.account.verdict, has_up, has_down):
            raise InvalidSummary("wording contradicts the account verdict")


def render_headline(text: str, facts: SummaryFacts) -> str:
    """Replace each id token with the location's name from the server-side map."""
    return _TOKEN.sub(lambda match: facts.names[match.group(1)], text)
