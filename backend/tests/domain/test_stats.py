"""Plan §2a: median, MAD and spread on hand-computed inputs."""

import pytest

from app.domain.stats import mad, median, spread


def test_s1_odd_length() -> None:
    # sorted 1,3,10 -> median 3; deviations 2,0,7 -> sorted 0,2,7 -> MAD 2
    assert median([1, 3, 10]) == 3
    assert mad([1, 3, 10]) == 2


def test_s2_even_length_averages_the_two_middle_values() -> None:
    # middle two 4,6 -> 5; deviations 3,1,1,3 -> sorted 1,1,3,3 -> MAD (1+3)/2 = 2
    assert median([2, 4, 6, 8]) == 5
    assert mad([2, 4, 6, 8]) == 2


def test_s2_unsorted_input() -> None:
    assert median([8, 2, 6, 4]) == 5


def test_s3_single_value() -> None:
    assert median([7]) == 7
    assert mad([7]) == 0


@pytest.mark.parametrize("fn", [median, mad, spread])
def test_s4_empty_raises(fn: object) -> None:
    with pytest.raises(ValueError):
        fn([])  # type: ignore[operator]


def test_s5_sqrt_median_wins() -> None:
    # MAD 0 -> max(0, sqrt(9) = 3, 1)
    assert spread([9] * 12) == 3.0


def test_s6_floor_of_one_wins() -> None:
    # MAD 0, sqrt(0) = 0 -> max(0, 0, 1)
    assert spread([0] * 8) == 1.0


def test_s7_scaled_mad_wins() -> None:
    # 1.4826 * 2 = 2.9652 vs sqrt(5) = 2.236 vs 1
    assert spread([2, 4, 6, 8]) == pytest.approx(2.9652, rel=1e-9)


def test_s8_floor_wins_over_both_terms_at_median_half() -> None:
    # median 0.5, deviations 0.5,0.5 -> MAD 0.5; 1.4826*0.5 = 0.7413; sqrt(0.5) = 0.7071 -> floor 1
    assert median([0, 1]) == 0.5
    assert mad([0, 1]) == 0.5
    assert spread([0, 1]) == 1.0
