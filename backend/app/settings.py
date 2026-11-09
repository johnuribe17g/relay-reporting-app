"""Typed settings: infrastructure (`Settings`) and the report parameters (`ReportSettings`)."""

from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.models import JudgeParams


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://relay:relay@localhost:5433/relay"
    test_database_url: str = "postgresql+psycopg://relay:relay@localhost:5433/relay_test"
    seed_path: Path = Path("/data/seed.sql")
    # Demo stand-in for login: the account used when X-Account-Id is missing (plans/T3, D-22).
    demo_account_id: int = 15


settings = Settings()


class ReportSettings(BaseSettings):
    """Business rules as configuration (PLAN §10). Defaults and reasoning: plans/T2 §1e, §1f."""

    model_config = SettingsConfigDict(env_prefix="REPORT_")

    baseline_weeks: int = Field(default=12, ge=1)
    min_history_weeks: int = Field(default=8, ge=1)
    z_min: float = Field(default=2.0, gt=0)
    min_abs: float = Field(default=3.0, ge=0)
    min_baseline_median: float = Field(default=4.0, ge=0)

    @model_validator(mode="after")
    def _history_fits_in_window(self) -> Self:
        if self.min_history_weeks > self.baseline_weeks:
            raise ValueError("min_history_weeks must not exceed baseline_weeks")
        return self

    def judge_params(self) -> JudgeParams:
        return JudgeParams(
            baseline_weeks=self.baseline_weeks,
            min_history_weeks=self.min_history_weeks,
            z_min=self.z_min,
            min_abs=self.min_abs,
            min_baseline_median=self.min_baseline_median,
        )


report_settings = ReportSettings()
