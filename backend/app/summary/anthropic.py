"""The real provider: one Messages API call over stdlib `urllib` (plans/T5-ai-summary.md §1e).

No tools and no sampling parameters. Thinking is left at the model default (Claude Haiku 5.5 thinks
adaptively), so the answer is read by block type, never by position, and `effort` is `low`. The key
is held in a private attribute and never put in a message, a log record or the repr.
"""

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Literal

from app.summary.providers import ProviderError, ProviderTimeout

logger = logging.getLogger(__name__)

URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"

Opener = Callable[..., Any]


class AnthropicProvider:
    name: Literal["mock", "anthropic"] = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        timeout: float,
        urlopen: Opener = urllib.request.urlopen,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._urlopen = urlopen

    def __repr__(self) -> str:
        return f"AnthropicProvider(model={self.model!r})"

    def _request(self, system: str, user: str) -> urllib.request.Request:
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"effort": "low"},
        }
        return urllib.request.Request(
            URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": API_VERSION,
            },
            method="POST",
        )

    def complete(self, system: str, user: str) -> str:
        try:
            with self._urlopen(self._request(system, user), timeout=self.timeout) as response:
                raw = response.read()
        except TimeoutError as exc:
            raise ProviderTimeout("the request timed out") from exc
        except urllib.error.HTTPError as exc:
            # The status only: the body is not needed and is never logged.
            raise ProviderError(f"HTTP {exc.code} from the provider") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise ProviderTimeout("the request timed out") from exc
            raise ProviderError("could not reach the provider") from exc
        except OSError as exc:
            raise ProviderError("network error") from exc
        return _text_of(raw)


def _text_of(raw: bytes) -> str:
    """The first `text` block of the response, or `ProviderError` for any unusable envelope."""
    try:
        envelope = json.loads(raw)
    except ValueError as exc:
        raise ProviderError("the response is not JSON") from exc
    if not isinstance(envelope, dict) or not isinstance(envelope.get("content"), list):
        raise ProviderError("the response has no content list")
    stop = envelope.get("stop_reason")
    if stop in ("max_tokens", "refusal"):
        raise ProviderError(f"the response stopped with {stop}")
    for block in envelope["content"]:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                return text
    raise ProviderError("the response has no text block")
