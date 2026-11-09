"""Plan §2f: report parameters, defaults, env overrides and validation."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.models import JudgeParams
from app.settings import ReportSettings

ENV_VARS = [
    "REPORT_BASELINE_WEEKS",
    "REPORT_MIN_HISTORY_WEEKS",
    "REPORT_Z_MIN",
    "REPORT_MIN_ABS",
    "REPORT_MIN_BASELINE_MEDIAN",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def make(**values: Any) -> ReportSettings:
    return ReportSettings(**values)


def test_defaults() -> None:
    s = make()
    assert (s.baseline_weeks, s.min_history_weeks) == (12, 8)
    assert (s.z_min, s.min_abs, s.min_baseline_median) == (2.0, 3.0, 4.0)


def test_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPORT_Z_MIN", "2.5")
    assert make().z_min == 2.5


def test_every_env_var_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPORT_BASELINE_WEEKS", "10")
    monkeypatch.setenv("REPORT_MIN_HISTORY_WEEKS", "5")
    monkeypatch.setenv("REPORT_Z_MIN", "1.5")
    monkeypatch.setenv("REPORT_MIN_ABS", "2")
    monkeypatch.setenv("REPORT_MIN_BASELINE_MEDIAN", "0")
    assert make().judge_params() == JudgeParams(10, 5, 1.5, 2.0, 0.0)


def test_judge_params_maps_every_field() -> None:
    s = make(baseline_weeks=6, min_history_weeks=4, z_min=3.0, min_abs=5.0, min_baseline_median=9.0)
    assert s.judge_params() == JudgeParams(
        baseline_weeks=6, min_history_weeks=4, z_min=3.0, min_abs=5.0, min_baseline_median=9.0
    )


def test_valid_smaller_window() -> None:
    s = make(baseline_weeks=6, min_history_weeks=4)
    assert (s.baseline_weeks, s.min_history_weeks) == (6, 4)


@pytest.mark.parametrize(
    "values",
    [
        {"baseline_weeks": 0},
        {"min_history_weeks": 0},
        {"min_history_weeks": 13},  # baseline 12
        {"baseline_weeks": 6},  # default min_history 8 > 6
        {"z_min": 0},
        {"z_min": -1},
        {"min_abs": -1},
        {"min_baseline_median": -1},
    ],
    ids=lambda v: ",".join(f"{k}={x}" for k, x in v.items()),
)
def test_invalid_values_are_rejected(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        make(**values)


def test_invalid_env_value_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPORT_Z_MIN", "0")
    with pytest.raises(ValidationError):
        make()
