"""The single-tier verdict (PLAN §2, D-02, D-08). Pure function, no I/O."""

from collections.abc import Sequence

from app.domain.models import Baseline, Judgement, JudgeParams, Verdict
from app.domain.stats import mad, median, spread


def judge(
    history: Sequence[int], x: int, params: JudgeParams, *, has_events: bool = True
) -> Judgement:
    """Judge week total `x` against the prior complete weeks in `history` (oldest first).

    Precedence, first match wins: no_activity, not_enough_history, too_quiet, then
    higher/lower/normal. `history` may hold more than `baseline_weeks` weeks; only the last
    `baseline_weeks` are used.
    """
    window = list(history[-params.baseline_weeks :])

    if not has_events:
        return Judgement(Verdict.NO_ACTIVITY, x, len(window), None, None, None)
    if len(window) < params.min_history_weeks:
        return Judgement(Verdict.NOT_ENOUGH_HISTORY, x, len(window), None, None, None)

    center = median(window)
    scale = spread(window)
    half_width = max(params.z_min * scale, params.min_abs)
    baseline = Baseline(
        median=center,
        mad=mad(window),
        spread=scale,
        weeks_used=len(window),
        band_low=center - half_width,
        band_high=center + half_width,
    )

    # Decided by the baseline median only, never by x.
    if center < params.min_baseline_median:
        return Judgement(Verdict.TOO_QUIET, x, len(window), baseline, None, None)

    diff = x - center
    z = diff / scale
    if abs(z) >= params.z_min and abs(diff) >= params.min_abs:
        verdict = Verdict.HIGHER if diff > 0 else Verdict.LOWER
    else:
        verdict = Verdict.NORMAL
    return Judgement(verdict, x, len(window), baseline, z, diff)
