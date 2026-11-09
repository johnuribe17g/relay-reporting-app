"""Plan §2b: verdict precedence, boundaries, window handling and the band."""

import pytest

from app.domain.models import Judgement, JudgeParams, Verdict
from app.domain.verdict import judge

DEFAULTS = JudgeParams(
    baseline_weeks=12, min_history_weeks=8, z_min=2.0, min_abs=3.0, min_baseline_median=4.0
)


def run(
    history: list[int],
    x: int,
    *,
    has_events: bool = True,
    min_abs: float = DEFAULTS.min_abs,
    min_baseline_median: float = DEFAULTS.min_baseline_median,
) -> Judgement:
    params = JudgeParams(
        baseline_weeks=DEFAULTS.baseline_weeks,
        min_history_weeks=DEFAULTS.min_history_weeks,
        z_min=DEFAULTS.z_min,
        min_abs=min_abs,
        min_baseline_median=min_baseline_median,
    )
    return judge(history, x, params, has_events=has_events)


def test_v1_boundary_z_equals_z_min_flags_higher() -> None:
    # median 9, MAD 0, spread 3; z = 6/3 = 2.0, d = 6
    result = run([9] * 12, 15)
    assert result.verdict is Verdict.HIGHER
    assert result.z == 2.0
    assert result.diff == 6


def test_v2_just_below_z_min_is_normal() -> None:
    result = run([9] * 12, 14)  # z = 5/3 = 1.667
    assert result.verdict is Verdict.NORMAL
    assert result.z == pytest.approx(1.667, rel=1e-3)


def test_v3_lower() -> None:
    result = run([9] * 12, 3)  # z = -6/3 = -2.0, d = -6
    assert result.verdict is Verdict.LOWER
    assert result.z == -2.0
    assert result.diff == -6


def test_v4_min_abs_guard_acts_alone() -> None:
    # z = 2.0 >= 2 but d = 6 < 7
    assert run([9] * 12, 15, min_abs=7).verdict is Verdict.NORMAL


def test_v5_min_abs_boundary_is_inclusive() -> None:
    assert run([9] * 12, 15, min_abs=6).verdict is Verdict.HIGHER


def test_v6_silent_week_is_lower() -> None:
    # spread sqrt(6) = 2.449; z = -6/2.449 = -2.449, d = -6
    result = run([6] * 12, 0)
    assert result.verdict is Verdict.LOWER
    assert result.z == pytest.approx(-2.449, rel=1e-3)
    assert result.diff == -6


def test_v7_median_exactly_at_threshold_is_judged() -> None:
    # median 4 (not < 4), spread 2, z = -2.0, d = -4
    result = run([4] * 12, 0)
    assert result.verdict is Verdict.LOWER
    assert result.z == -2.0
    assert result.diff == -4


def test_v8_median_below_threshold_is_too_quiet() -> None:
    # sorted 6x3, 6x4 -> median (3+4)/2 = 3.5 < 4
    result = run([3, 4] * 6, 0)
    assert result.verdict is Verdict.TOO_QUIET
    assert result.z is None
    assert result.baseline is not None
    assert result.baseline.median == 3.5


def test_v9_x_never_decides_too_quiet() -> None:
    assert run([2] * 12, 50).verdict is Verdict.TOO_QUIET


def test_v10_floor_of_one_is_reachable_when_quiet_threshold_is_zero() -> None:
    # median 0, spread 1 (floor wins); z = 3.0, d = 3
    result = run([0] * 8, 3, min_baseline_median=0)
    assert result.verdict is Verdict.HIGHER
    assert result.z == 3.0
    assert result.baseline is not None
    assert result.baseline.spread == 1.0


def test_v11_seven_prior_weeks_is_not_enough_history() -> None:
    result = run([5] * 7, 5)
    assert result.verdict is Verdict.NOT_ENOUGH_HISTORY
    assert result.baseline is None
    assert result.z is None


def test_v12_eight_prior_weeks_is_judged() -> None:
    result = run([5] * 8, 5)
    assert result.verdict is Verdict.NORMAL
    assert result.baseline is not None
    assert result.baseline.weeks_used == 8
    assert result.history_weeks == 8


def test_v13_eleven_prior_weeks_uses_all_eleven() -> None:
    result = run([5] * 11, 5)
    assert result.baseline is not None
    assert result.baseline.weeks_used == 11


def test_v14_only_the_last_baseline_weeks_count() -> None:
    # 14 weeks given; window = last 12 -> median 5, the older 100s are ignored
    result = run([100, 100] + [5] * 12, 5)
    assert result.verdict is Verdict.NORMAL
    assert result.baseline is not None
    assert result.baseline.weeks_used == 12
    assert result.baseline.median == 5


def test_v15_no_events_is_no_activity() -> None:
    result = run([], 0, has_events=False)
    assert result.verdict is Verdict.NO_ACTIVITY
    assert result.baseline is None


def test_v15_no_activity_wins_even_with_history() -> None:
    assert run([9] * 12, 15, has_events=False).verdict is Verdict.NO_ACTIVITY


def test_v16_not_enough_history_takes_precedence_over_too_quiet() -> None:
    # 7 < 8 and median 1 < 4
    assert run([1] * 7, 0).verdict is Verdict.NOT_ENOUGH_HISTORY


def test_v17_account_starting_after_the_week_has_no_history() -> None:
    assert run([], 0, has_events=True).verdict is Verdict.NOT_ENOUGH_HISTORY


def test_v18_band_is_the_no_flag_region() -> None:
    # h = max(2*3, 3) = 6 -> band (3, 15)
    result = run([9] * 12, 15)
    assert result.baseline is not None
    assert result.baseline.band_low == 3.0
    assert result.baseline.band_high == 15.0
    assert run([9] * 12, 14).verdict is Verdict.NORMAL  # inside the band
    assert result.verdict is Verdict.HIGHER  # on the edge: outside


def test_v19_band_with_poisson_floor() -> None:
    # h = max(2*2.449 = 4.899, 3) -> band (1.101, 10.899)
    result = run([6] * 12, 6)
    assert result.baseline is not None
    assert result.baseline.band_low == pytest.approx(1.101, rel=1e-3)
    assert result.baseline.band_high == pytest.approx(10.899, rel=1e-3)
