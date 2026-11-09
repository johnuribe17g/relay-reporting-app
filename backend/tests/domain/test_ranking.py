"""Plan §2c: ranking by |z|, then |diff|, then name; unjudged last by name."""

import random

from app.domain.models import Judgement, Verdict
from app.domain.ranking import rank


def judged(z: float, diff: float) -> Judgement:
    verdict = Verdict.NORMAL if abs(z) < 2 else (Verdict.HIGHER if z > 0 else Verdict.LOWER)
    return Judgement(verdict, 0, 12, None, z, diff)


def unjudged(verdict: Verdict) -> Judgement:
    return Judgement(verdict, 0, 3, None, None, None)


def names(items: list[tuple[str, Judgement]]) -> list[str]:
    return [name for name, _ in items]


def test_r1_orders_by_absolute_z_ignoring_sign() -> None:
    items = [("C", judged(0.5, 1)), ("A", judged(-3.0, -6)), ("B", judged(2.0, 5))]
    assert names(rank(items)) == ["A", "B", "C"]


def test_r2_tie_on_z_breaks_by_larger_absolute_diff() -> None:
    items = [("A", judged(3.0, 5)), ("B", judged(-3.0, -6))]
    assert names(rank(items)) == ["B", "A"]


def test_r3_full_tie_breaks_by_name() -> None:
    items = [("D", judged(2.0, 4)), ("C", judged(2.0, 4)), ("E", judged(2.0, 4))]
    assert names(rank(items)) == ["C", "D", "E"]


def test_r4_unjudged_go_after_judged_by_name() -> None:
    items = [
        ("B", unjudged(Verdict.TOO_QUIET)),
        ("X", judged(0.1, 1)),
        ("A", unjudged(Verdict.NOT_ENOUGH_HISTORY)),
    ]
    assert names(rank(items)) == ["X", "A", "B"]


def test_r5_output_is_independent_of_input_order() -> None:
    items = [
        ("A", judged(3.0, 5)),
        ("B", judged(-3.0, -6)),
        ("C", judged(2.0, 4)),
        ("D", judged(2.0, 4)),
        ("E", unjudged(Verdict.TOO_QUIET)),
        ("F", unjudged(Verdict.NOT_ENOUGH_HISTORY)),
    ]
    expected = names(rank(items))
    assert expected == ["B", "A", "C", "D", "E", "F"]
    rng = random.Random(0)
    for _ in range(5):
        shuffled = items[:]
        rng.shuffle(shuffled)
        assert names(rank(shuffled)) == expected


def test_r6_empty() -> None:
    assert rank([]) == []
