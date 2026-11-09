"""Providers behind one interface (plans/T5-ai-summary.md §1d). The mock needs no key or network."""

import json
import logging
import re
from typing import Any, Literal, Protocol

from app.settings import MockMode, SummarySettings

logger = logging.getLogger(__name__)

_DATA_BLOCK = re.compile(r"<data>(.*)</data>", re.DOTALL)


class ProviderError(Exception):
    """The provider failed (network, HTTP error, unusable envelope)."""


class ProviderTimeout(ProviderError):
    """The provider did not answer in time."""


class Provider(Protocol):
    name: Literal["mock", "anthropic"]

    def complete(self, system: str, user: str) -> str: ...


def _headline(payload: dict[str, Any]) -> str:
    """A deterministic headline that follows the prompt's rules (no digits, ids only)."""
    verdict = payload["account"]["verdict"]
    flagged = payload["flagged_total"]
    locations = payload["locations"]
    word = verdict if verdict in ("higher", "lower") else None
    if word is not None:
        if flagged >= 2:
            return (
                f"The whole account is {word} than usual, across several locations. "
                "Start with [L1]."
            )
        if flagged == 1:
            return f"The account total is {word} than usual. Start with [L1]."
        return f"The account total is {word} than usual, with no single location standing out."
    if verdict == "normal":
        if flagged >= 2:
            return (
                "Several locations are off their usual level while the account total is normal. "
                "Start with [L1]."
            )
        if flagged == 1:
            return (
                f"A single-location pattern: [L1] is {locations[0]['verdict']} than usual "
                "and the rest of the account looks normal."
            )
        return "Nothing stands out this week."
    return "There is not enough information to say more."


def _flip(verdict: str) -> str:
    return "lower" if verdict == "higher" else "higher"


class MockProvider:
    """Answers like a model that follows the prompt, reading the same `<data>` block.

    `mode` forces exactly one defect so every fallback can be exercised offline.
    """

    name: Literal["mock", "anthropic"] = "mock"

    def __init__(self, mode: MockMode = "ok") -> None:
        self.mode = mode

    def complete(self, system: str, user: str) -> str:
        if self.mode == "exception":
            raise RuntimeError("mock provider failure")
        if self.mode == "timeout":
            raise ProviderTimeout("mock provider timeout")
        if self.mode == "malformed_json":
            return "not json {"
        match = _DATA_BLOCK.search(user)
        if match is None:
            raise ProviderError("no data block in the prompt")
        payload = json.loads(match.group(1))
        claims: list[dict[str, Any]] = [
            {
                "scope": "account",
                "location": None,
                "metric": "total",
                "verdict": payload["account"]["verdict"],
            }
        ]
        claims += [
            {
                "scope": "location",
                "location": loc["id"],
                "metric": "total",
                "verdict": loc["verdict"],
            }
            for loc in payload["locations"]
        ]
        if self.mode == "unknown_location":
            claims.append(
                {"scope": "location", "location": "L9", "metric": "total", "verdict": "higher"}
            )
        elif self.mode == "contradicting_verdict":
            target = claims[1] if len(claims) > 1 else claims[0]
            target["verdict"] = _flip(target["verdict"])
        return json.dumps({"headline": _headline(payload), "claims": claims})


def select_provider(settings: SummarySettings) -> Provider:
    """The effective provider. A missing key never raises: it falls back to the mock and warns."""
    if settings.summary_provider == "anthropic":
        if settings.anthropic_api_key is None:
            logger.warning("SUMMARY_PROVIDER=anthropic but no ANTHROPIC_API_KEY: using the mock")
        else:
            from app.summary.anthropic import AnthropicProvider  # avoids a circular import

            return AnthropicProvider(
                api_key=settings.anthropic_api_key.get_secret_value(),
                model=settings.summary_model,
                max_tokens=settings.summary_max_tokens,
                timeout=settings.summary_timeout_seconds,
            )
    return MockProvider(settings.summary_mock_mode)
