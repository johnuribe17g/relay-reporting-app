"""Ranking of locations by how far they deviate from their own normal (PLAN §2)."""

from collections.abc import Sequence

from app.domain.models import Judgement


def _key(item: tuple[str, Judgement]) -> tuple[int, float, float, str]:
    name, judgement = item
    if judgement.z is None or judgement.diff is None:
        return (1, 0.0, 0.0, name)  # not judged: after all judged items, by name
    return (0, -abs(judgement.z), -abs(judgement.diff), name)


def rank(items: Sequence[tuple[str, Judgement]]) -> list[tuple[str, Judgement]]:
    """Judged items by |z| desc, then |diff| desc, then name asc; unjudged after, by name."""
    return sorted(items, key=_key)
