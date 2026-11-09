"""The fallback ladder (plans/T5-ai-summary.md §1a): the model's output is never trusted."""

import logging

from app.schemas import Report, SummaryOut, SummaryReason
from app.settings import SummarySettings
from app.summary.claims import validate_summary
from app.summary.errors import InvalidSummary
from app.summary.facts import SummaryFacts, build_facts
from app.summary.prompt import PROMPT_VERSION, build_prompt
from app.summary.providers import Provider, ProviderError, ProviderTimeout
from app.summary.render import fact_lines, template_lines

logger = logging.getLogger(__name__)


def _template(facts: SummaryFacts, provider: Provider, reason: SummaryReason) -> SummaryOut:
    return SummaryOut(
        week=facts.week,
        headline=None,
        text="\n".join(template_lines(facts)),
        source="template",
        reason=reason,
        provider=provider.name,
        prompt_version=PROMPT_VERSION,
    )


def summarize(report: Report, settings: SummarySettings, provider: Provider) -> SummaryOut:
    facts = build_facts(report)
    if facts.week is None:
        return _template(facts, provider, "nothing_to_summarize")
    if not settings.llm_summary_enabled:
        return _template(facts, provider, "disabled")
    system, user = build_prompt(facts)
    try:
        raw = provider.complete(system, user)
    except ProviderError as exc:
        # Our own adapter messages (a status code, "timed out"): no key, no response body.
        logger.warning("summary provider failed: %s: %s", type(exc).__name__, exc)
        return _template(
            facts, provider, "timeout" if isinstance(exc, ProviderTimeout) else "provider_error"
        )
    except Exception as exc:  # a provider must never turn into a 500; any other: the type only
        logger.warning("summary provider failed: %s", type(exc).__name__)
        return _template(facts, provider, "provider_error")
    try:
        valid = validate_summary(raw, facts)
    except InvalidSummary as exc:
        # The message can hold model-controlled text: log a short prefix only.
        logger.warning("summary rejected: %.100s", str(exc))
        return _template(facts, provider, "validation_failed")
    return SummaryOut(
        week=facts.week,
        headline=valid.headline,
        text="\n".join(fact_lines(facts, valid.claims)),
        source="ai",
        reason=None,
        provider=provider.name,
        prompt_version=PROMPT_VERSION,
    )
