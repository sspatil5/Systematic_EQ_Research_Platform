"""Typed YAML configuration loading."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str
    end: str | None = None
    auto_adjust: bool = True
    cache_dir: Path = Path("data/cache")
    processed_path: Path = Path("data/processed/daily_panel.parquet")
    refresh: bool = False


class ValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_abs_daily_return: float = Field(default=0.80, gt=0)
    max_missing_session_fraction: float = Field(default=0.10, ge=0, le=1)
    allow_zero_volume: bool = True


class FeatureConfig(BaseModel):
    """Phase 2 research choices; tuple fields preserve deterministic ordering."""

    model_config = ConfigDict(extra="forbid")

    output_path: Path = Path("data/processed/features.parquet")
    enabled_groups: tuple[str, ...] = (
        "momentum", "mean_reversion", "volatility", "volume", "market"
    )
    return_lookbacks: tuple[int, ...] = (1, 2, 5, 10, 20, 60, 120, 252)
    moving_average_windows: tuple[int, ...] = (5, 10, 20, 50, 100, 200)
    volatility_windows: tuple[int, ...] = (5, 10, 20, 60)
    market_benchmark: str = "SPY"
    target_horizons: tuple[int, ...] = (1, 5, 10, 20)
    primary_target: str = "target_return_5d"
    rank_target_horizons: tuple[int, ...] = (5,)
    excess_target_horizons: tuple[int, ...] = (5,)
    cross_sectional_features: tuple[str, ...] = (
        "ret_20d", "ret_60d", "realized_vol_20", "volume_zscore_20",
        "excess_market_return_1d",
    )
    cross_sectional_transforms: tuple[str, ...] = ("rank", "zscore")
    min_cross_sectional_observations: int = Field(default=2, ge=2)

    @field_validator(
        "return_lookbacks", "moving_average_windows", "volatility_windows", "target_horizons",
        "rank_target_horizons", "excess_target_horizons",
    )
    @classmethod
    def positive_unique_windows(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        if any(value <= 0 for value in values):
            raise ValueError("All lookbacks and horizons must be positive")
        if len(values) != len(set(values)):
            raise ValueError("Lookbacks and horizons must not contain duplicates")
        return values

    @model_validator(mode="after")
    def target_configuration_is_consistent(self) -> "FeatureConfig":
        horizons = set(self.target_horizons)
        if not set(self.rank_target_horizons).issubset(horizons):
            raise ValueError("rank_target_horizons must be included in target_horizons")
        if not set(self.excess_target_horizons).issubset(horizons):
            raise ValueError("excess_target_horizons must be included in target_horizons")
        return self


class CandidateSignalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    expected_direction: int = Field(default=0, ge=-1, le=1)


class BootstrapConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    iterations: int = Field(default=1000, ge=100)
    block_length: int = Field(default=20, ge=1)
    seed: int = 42


class ClassificationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_abs_ic: float = Field(default=0.02, ge=0)
    promising_fdr: float = Field(default=0.10, gt=0, le=1)
    strong_fdr: float = Field(default=0.05, gt=0, le=1)
    minimum_positive_year_fraction: float = Field(default=0.60, ge=0, le=1)
    maximum_daily_turnover: float = Field(default=0.75, ge=0, le=1)


class SignalResearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_dir: Path = Path("reports/phase3")
    primary_target: str = "target_return_5d"
    target_horizon: int = Field(default=5, ge=1)
    horizons: tuple[int, ...] = (1, 5, 10, 20)
    quantiles: int = Field(default=5, ge=2)
    minimum_cross_section: int = Field(default=20, ge=3)
    hac_lags: int = Field(default=4, ge=0)
    correlation_flag_threshold: float = Field(default=0.80, gt=0, le=1)
    liquidity_feature: str = "avg_dollar_volume_20"
    high_liquidity_fraction: float = Field(default=0.50, gt=0, lt=1)
    fdr_alpha: float = Field(default=0.05, gt=0, le=1)
    bonferroni_alpha: float = Field(default=0.05, gt=0, le=1)
    bootstrap: BootstrapConfig = BootstrapConfig()
    classification: ClassificationConfig = ClassificationConfig()
    candidates: tuple[CandidateSignalConfig, ...] = (
        CandidateSignalConfig(name="ret_1d", expected_direction=-1),
        CandidateSignalConfig(name="ret_5d", expected_direction=-1),
        CandidateSignalConfig(name="ret_20d", expected_direction=1),
        CandidateSignalConfig(name="ret_60d", expected_direction=1),
        CandidateSignalConfig(name="ret_120d", expected_direction=1),
        CandidateSignalConfig(name="momentum_12_1", expected_direction=1),
        CandidateSignalConfig(name="price_to_sma_20", expected_direction=0),
        CandidateSignalConfig(name="price_to_sma_50", expected_direction=0),
        CandidateSignalConfig(name="return_zscore_5", expected_direction=-1),
        CandidateSignalConfig(name="realized_vol_20", expected_direction=0),
        CandidateSignalConfig(name="downside_vol_20", expected_direction=0),
        CandidateSignalConfig(name="volume_zscore_20", expected_direction=0),
        CandidateSignalConfig(name="relative_volume_20", expected_direction=0),
        CandidateSignalConfig(name="beta_20", expected_direction=0),
        CandidateSignalConfig(name="residual_return_1d", expected_direction=-1),
        CandidateSignalConfig(name="relative_momentum_20", expected_direction=1),
        CandidateSignalConfig(name="relative_momentum_60", expected_direction=1),
    )

    @model_validator(mode="after")
    def unique_safe_candidates(self) -> "SignalResearchConfig":
        names = [candidate.name for candidate in self.candidates]
        if len(names) != len(set(names)):
            raise ValueError("Candidate signal names must be unique")
        if any(name.startswith("target_") for name in names):
            raise ValueError("Target columns cannot be candidate signals")
        return self


class AlphaResearchConfig(BaseModel):
    """Frozen Phase 3.5 post-selection research design."""

    model_config = ConfigDict(extra="forbid")

    output_dir: Path = Path("reports/phase3_5")
    development_end: str = "2021-12-31"
    confirmation_start: str = "2022-01-01"
    target: str = "target_return_5d"
    minimum_cross_section: int = Field(default=20, ge=10)
    minimum_sector_size: int = Field(default=3, ge=2)
    hac_lags: int = Field(default=4, ge=0)
    fdr_alpha: float = Field(default=0.05, gt=0, le=1)
    reversal_tail_fractions: tuple[float, ...] = (0.05, 0.10, 0.20)


class BacktestResearchConfig(BaseModel):
    """Frozen Phase 4 execution and robustness design."""

    model_config = ConfigDict(extra="forbid")

    output_dir: Path = Path("reports/phase4")
    initial_cash: float = Field(default=30_000.0, gt=0)
    primary_signal: str = "sector_neutral_momentum_12_1"
    challenger_signal: str = "combined_momentum_volatility"
    top_n: int = 10
    rebalance_frequency: str = "weekly"
    execution_mode: str = "next_open"
    primary_cost_bps: float = 5.0
    liquidity_floor: float = 20_000_000.0
    fractional_shares: bool = False
    top_n_sensitivity: tuple[int, ...] = (5, 10, 20)
    frequency_sensitivity: tuple[str, ...] = ("daily", "weekly", "10_sessions", "monthly")
    cost_sensitivity_bps: tuple[float, ...] = (0, 2, 5, 10, 20)
    break_even_cost_bps: tuple[float, ...] = (0, 2, 5, 10, 20, 30, 40, 50)
    delay_modes: tuple[str, ...] = ("next_open", "next_close", "second_open")
    random_simulations: int = Field(default=100, ge=10)
    random_seed: int = 42

    @model_validator(mode="after")
    def frozen_signal_definitions(self) -> "BacktestResearchConfig":
        if self.primary_signal != "sector_neutral_momentum_12_1":
            raise ValueError("Phase 4 primary signal is frozen")
        if self.challenger_signal != "combined_momentum_volatility":
            raise ValueError("Phase 4 challenger signal is frozen")
        return self


class ResearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: DataConfig
    validation: ValidationConfig = ValidationConfig()
    features: FeatureConfig = FeatureConfig()
    signal_research: SignalResearchConfig = SignalResearchConfig()
    alpha_research: AlphaResearchConfig = AlphaResearchConfig()
    backtest: BacktestResearchConfig = BacktestResearchConfig()


def load_research_config(path: str | Path = "config/research.yaml") -> ResearchConfig:
    with Path(path).open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    return ResearchConfig.model_validate(payload)
