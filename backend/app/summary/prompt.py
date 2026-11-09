"""The versioned prompt (plans/T5-ai-summary.md §1b): a file, read once at import."""

import json
from pathlib import Path
from typing import Final

from app.summary.facts import SummaryFacts, prompt_payload

PROMPT_FILE: Final = Path(__file__).parent / "prompts" / "summary-v1.md"
PROMPT_VERSION: Final = PROMPT_FILE.stem
SYSTEM_PROMPT: Final = PROMPT_FILE.read_text(encoding="utf-8")

_ESCAPES = {"<": "\\u003c", ">": "\\u003e", "&": "\\u0026"}


def escape_json(text: str) -> str:
    """Keep `<`, `>` and `&` out of the serialized data, so it cannot close its own block.

    Hygiene only: no free text is sent (locations go by id), which is the real guarantee.
    """
    return "".join(_ESCAPES.get(char, char) for char in text)


def data_block(facts: SummaryFacts) -> str:
    return (
        "<data>" + escape_json(json.dumps(prompt_payload(facts), separators=(",", ":"))) + "</data>"
    )


def build_prompt(facts: SummaryFacts) -> tuple[str, str]:
    """`(system, user)`: the versioned instructions and the data block."""
    return SYSTEM_PROMPT, data_block(facts)
