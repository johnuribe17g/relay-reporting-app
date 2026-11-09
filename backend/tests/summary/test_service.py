"""The fallback ladder, providers and settings (plans/T5-ai-summary.md §2c, P3). No DB, no HTTP."""

import logging
from typing import Any, Literal

import pytest

from app.domain.models import Verdict
from app.schemas import Report
from app.settings import MockMode, SummarySettings
from app.summary.claims import validate_summary
from app.summary.facts import build_facts
from app.summary.prompt import build_prompt
from app.summary.providers import MockProvider, Provider, select_provider
from app.summary.service import summarize
from tests.summary import builders as b
from tests.summary.test_render import F1_LINES, NO_FLAGS

ON = SummarySettings(llm_summary_enabled=True)
OFF = SummarySettings(llm_summary_enabled=False)
F1_TEXT = "\n".join(F1_LINES)
F1_HEADLINE = (
    "A single-location pattern: Site C is higher than usual "
    "and the rest of the account looks normal."
)


class Recorder:
    """A fake provider that counts calls and returns or raises what it was given."""

    name: Literal["mock", "anthropic"] = "mock"

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result  # type: ignore[no-any-return]


def mock(mode: MockMode) -> Provider:
    return MockProvider(mode)


def test_s1_flag_off_never_calls_the_provider() -> None:
    provider = Recorder()
    out = summarize(b.f1(), OFF, provider)
    assert (out.source, out.reason, out.provider) == ("template", "disabled", "mock")
    assert out.prompt_version == "summary-v1"
    assert out.headline is None and out.text == F1_TEXT
    assert provider.calls == 0


def test_s2_ok_gives_an_ai_summary_with_a_headline() -> None:
    out = summarize(b.f1(), ON, mock("ok"))
    assert (out.source, out.reason, out.provider) == ("ai", None, "mock")
    assert out.headline == F1_HEADLINE
    assert out.text == F1_TEXT


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
def test_s3_to_s7_one_fallback_per_reason(mode: MockMode, reason: str) -> None:
    out = summarize(b.f1(), ON, mock(mode))
    assert (out.source, out.reason, out.headline) == ("template", reason, None)
    assert out.text == F1_TEXT


def test_s8_edge_reports() -> None:
    nothing = "Nothing stands out this week."
    several = (
        "Several locations are off their usual level while the account total is normal. "
        "Start with Loc1."
    )
    for report, headline, lines in (
        (b.f2(), nothing, [F1_LINES[0], NO_FLAGS]),
        (b.f3(), nothing, [F1_LINES[0], NO_FLAGS, "Locations that could not be judged: 3."]),
    ):
        out = summarize(report, ON, mock("ok"))
        assert (out.source, out.headline, out.text) == ("ai", headline, "\n".join(lines))
    spike = summarize(b.f4(), ON, mock("ok"))
    assert spike.source == "ai" and spike.headline == several
    assert spike.text.splitlines()[-1] == "More flagged locations not listed: 2."


def test_s9_a_provider_never_causes_a_500() -> None:
    assert summarize(b.f1(), ON, Recorder(error=KeyError("x"))).reason == "provider_error"
    assert summarize(b.f1(), ON, Recorder(result=None)).reason == "validation_failed"


def test_s11_missing_key_falls_back_to_the_mock_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = SummarySettings(summary_provider="anthropic", anthropic_api_key=None)
    with caplog.at_level(logging.WARNING):
        provider = select_provider(settings)
    assert isinstance(provider, MockProvider) and provider.name == "mock"
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1
    assert summarize(b.f1(), ON, provider).provider == "mock"
    assert isinstance(select_provider(SummarySettings(summary_provider="mock")), MockProvider)


def test_s12_settings_defaults_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "LLM_SUMMARY_ENABLED",
        "SUMMARY_PROVIDER",
        "ANTHROPIC_API_KEY",
        "SUMMARY_MOCK_MODE",
    ):
        monkeypatch.delenv(var, raising=False)
    clean = SummarySettings()
    assert clean.llm_summary_enabled is False and clean.summary_provider == "mock"
    assert clean.anthropic_api_key is None and clean.summary_mock_mode == "ok"
    monkeypatch.setenv("LLM_SUMMARY_ENABLED", "true")
    assert SummarySettings().llm_summary_enabled is True
    monkeypatch.setenv("SUMMARY_PROVIDER", "nope")
    with pytest.raises(ValueError):
        SummarySettings()


@pytest.mark.parametrize(
    "report", [b.empty_report(Verdict.NO_ACTIVITY), b.empty_report(Verdict.NOT_ENOUGH_HISTORY)]
)
@pytest.mark.parametrize("settings", [ON, OFF])
def test_s13_week_null_is_nothing_to_summarize(report: Report, settings: SummarySettings) -> None:
    provider = Recorder()
    out = summarize(report, settings, provider)
    assert (out.source, out.reason, out.headline, out.week) == (
        "template",
        "nothing_to_summarize",
        None,
        None,
    )
    assert out.text in (
        "No activity has been recorded for this account.",
        "No week can be judged yet for this account: not enough history.",
    )
    assert provider.calls == 0


def test_p3_the_mock_reads_the_same_data_block() -> None:
    facts = build_facts(b.f4())
    raw = MockProvider("ok").complete(*build_prompt(facts))
    valid = validate_summary(raw, facts)
    assert [c.location for c in valid.claims] == [None, "L1", "L2", "L3", "L4", "L5"]
    assert valid.headline == (
        "Several locations are off their usual level while the account total is normal. "
        "Start with Loc1."
    )
