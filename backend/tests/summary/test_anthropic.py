"""The real adapter with an injected `urlopen` (plans/T5-ai-summary.md §2f, X1 to X5).

No network and no key.

The response shapes follow the claude-api skill: content is a list of blocks read by `type` (Claude
Haiku 5.5 thinks by default, so a `thinking` block can come first), `stop_reason` can be
`max_tokens` or `refusal`.
"""

import json
import logging
import urllib.error
from typing import Any

import pytest
from pydantic import SecretStr

from app.settings import SummarySettings
from app.summary.anthropic import API_VERSION, URL, AnthropicProvider
from app.summary.facts import build_facts
from app.summary.prompt import build_prompt
from app.summary.providers import ProviderError, ProviderTimeout, select_provider
from app.summary.service import summarize
from tests.summary import builders as b

KEY = "sk-ant-fake-key-123"
ON = SummarySettings(llm_summary_enabled=True)
GOOD = json.dumps(
    {
        "headline": "Nothing stands out this week.",
        "claims": [{"scope": "account", "location": None, "metric": "total", "verdict": "normal"}],
    }
)


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def envelope(text: str = GOOD, **over: Any) -> bytes:
    body: dict[str, Any] = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
    }
    body.update(over)
    return json.dumps(body).encode()


class Opener:
    """Records the request and the timeout; answers with a body or raises."""

    def __init__(self, body: bytes = b"", error: BaseException | None = None) -> None:
        self.body = body
        self.error = error
        self.requests: list[Any] = []
        self.timeouts: list[float] = []

    def __call__(self, request: Any, timeout: float) -> FakeResponse:
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.error is not None:
            raise self.error
        return FakeResponse(self.body)


def provider(opener: Opener) -> AnthropicProvider:
    return AnthropicProvider(KEY, "claude-haiku-5-5", 777, 3.5, urlopen=opener)


def test_x1_the_request() -> None:
    opener = Opener(envelope())
    provider(opener).complete("SYSTEM", "USER")
    request = opener.requests[0]
    assert request.full_url == URL == "https://api.anthropic.com/v1/messages"
    assert request.get_method() == "POST"
    headers = {k.lower(): v for k, v in request.header_items()}
    assert headers["x-api-key"] == KEY
    assert headers["anthropic-version"] == API_VERSION
    assert headers["content-type"] == "application/json"
    body = json.loads(request.data)
    assert body["model"] == "claude-haiku-5-5"
    assert body["max_tokens"] == 777
    assert body["system"] == "SYSTEM"
    assert body["messages"] == [{"role": "user", "content": "USER"}]
    assert "tools" not in body and "tool_choice" not in body
    assert not {"temperature", "top_p", "top_k"} & body.keys()
    assert opener.timeouts == [3.5]


def test_x2_the_text_block_is_read_by_type() -> None:
    assert provider(Opener(envelope())).complete("s", "u") == GOOD
    thinking_first = envelope(
        content=[
            {"type": "thinking", "thinking": "", "signature": "abc"},
            {"type": "text", "text": GOOD},
        ]
    )
    assert provider(Opener(thinking_first)).complete("s", "u") == GOOD


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError("slow"), ProviderTimeout),
        (urllib.error.URLError(TimeoutError("slow")), ProviderTimeout),
        (urllib.error.HTTPError(URL, 500, "boom", {}, None), ProviderError),  # type: ignore[arg-type]
        (urllib.error.URLError("no route"), ProviderError),
        (ConnectionResetError("reset"), ProviderError),
    ],
)
def test_x3_failures(error: BaseException, expected: type[Exception]) -> None:
    with pytest.raises(expected) as caught:
        provider(Opener(error=error)).complete("s", "u")
    assert type(caught.value) is expected  # a timeout is not reported as a plain error


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"{}",
        b'{"content": "x"}',
        b'{"content": []}',
        b'{"content": [{"type": "thinking", "thinking": "", "signature": "s"}]}',
        envelope(stop_reason="max_tokens"),
        envelope(stop_reason="refusal"),
    ],
)
def test_x3_a_bad_envelope_is_a_provider_error(body: bytes) -> None:
    with pytest.raises(ProviderError):
        provider(Opener(body)).complete("s", "u")


def test_x4_the_key_is_never_in_a_message_a_log_or_the_repr(
    caplog: pytest.LogCaptureFixture,
) -> None:
    leaky = [
        urllib.error.HTTPError(URL, 401, f"bad key {KEY}", {}, None),  # type: ignore[arg-type]
        urllib.error.URLError(f"cannot reach {KEY}"),
        TimeoutError(KEY),
        OSError(KEY),
    ]
    with caplog.at_level(logging.DEBUG):
        for error in leaky:
            with pytest.raises(ProviderError) as caught:
                provider(Opener(error=error)).complete("s", "u")
            assert KEY not in str(caught.value)
        result = summarize(b.f1(), ON, provider(Opener(error=TimeoutError(KEY))))
    assert result.reason == "timeout"
    assert KEY not in caplog.text
    assert "summary provider failed: ProviderTimeout: the request timed out" in caplog.text
    assert KEY not in repr(provider(Opener()))


def test_x5_the_service_validates_what_the_adapter_returns() -> None:
    facts = build_facts(b.f1())
    system, user = build_prompt(facts)
    assert system and user
    # Valid for F1 facts: the account claim and the one listed location.
    claims = [
        {"scope": "account", "location": None, "metric": "total", "verdict": "normal"},
        {"scope": "location", "location": "L1", "metric": "total", "verdict": "higher"},
    ]
    good = json.dumps({"headline": "[L1] is higher than usual.", "claims": claims})
    ok = summarize(b.f1(), ON, provider(Opener(envelope(good))))
    assert (ok.source, ok.reason, ok.provider) == ("ai", None, "anthropic")
    assert ok.headline == "Site C is higher than usual."
    # No account claim and a missing location claim: rejected, the template shows.
    bad = summarize(b.f1(), ON, provider(Opener(envelope(GOOD))))
    assert (bad.source, bad.reason, bad.provider) == ("template", "validation_failed", "anthropic")
    assert bad.headline is None


def test_s11_with_a_key_the_anthropic_provider_is_selected_without_a_call() -> None:
    settings = SummarySettings(summary_provider="anthropic", anthropic_api_key=SecretStr(KEY))
    chosen = select_provider(settings)
    assert isinstance(chosen, AnthropicProvider) and chosen.name == "anthropic"
    assert (chosen.model, chosen.max_tokens, chosen.timeout) == ("claude-haiku-5-5", 1024, 5.0)
    assert KEY not in repr(chosen)
