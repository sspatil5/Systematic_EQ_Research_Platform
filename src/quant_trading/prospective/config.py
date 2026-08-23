"""Frozen Phase 5 configuration models."""

from pathlib import Path
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class UniverseRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    security_types: tuple[str, ...]
    allowed_exchanges: tuple[str, ...]
    minimum_price: float = Field(gt=0)
    minimum_trailing_dollar_volume: float = Field(gt=0)
    minimum_history_sessions: int = Field(ge=252)
    sector_required: bool = True


class PortfolioRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    size: int = Field(default=10, gt=0)
    rebalance_frequency: str
    initial_equity: float = Field(default=30_000, gt=0)
    whole_shares: bool = True
    long_only: bool = True
    leverage: bool = False


class ExecutionRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str
    cost_bps: float = Field(ge=0)
    missing_open_policy: str


class ProspectiveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiment_id: str
    created_at: str
    timezone: str
    provider: str
    universe: UniverseRules
    portfolio: PortfolioRules
    execution: ExecutionRules
    cost_scenarios_bps: tuple[float, ...]
    signals: dict[str, str]
    checkpoints_months: tuple[int, ...]
    storage_root: Path
    report_root: Path

    @model_validator(mode="after")
    def frozen_design(self):
        if self.signals != {"primary": "sector_neutral_momentum_12_1",
                            "challenger": "combined_momentum_volatility"}:
            raise ValueError("Only the two frozen Phase 5 signals are permitted")
        if self.cost_scenarios_bps != (0, 2, 5, 10, 20):
            raise ValueError("Phase 5 cost scenarios are frozen")
        if not (self.portfolio.whole_shares and self.portfolio.long_only and not self.portfolio.leverage):
            raise ValueError("Phase 5 portfolio constraints are frozen")
        return self


def load_prospective_config(path="config/prospective.yaml") -> ProspectiveConfig:
    with Path(path).open(encoding="utf-8") as handle:
        return ProspectiveConfig.model_validate(yaml.safe_load(handle))
