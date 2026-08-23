"""Deterministic orchestration of Phase 2 features and targets."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_trading.features.common import trailing_returns, validate_input_panel
from quant_trading.features.cross_sectional import apply_cross_sectional_transforms
from quant_trading.features.market import build_market_features
from quant_trading.features.mean_reversion import build_mean_reversion_features
from quant_trading.features.metadata import FeatureMetadata, base_metadata, transformed_metadata
from quant_trading.features.momentum import build_momentum_features
from quant_trading.features.validation import DatasetSummary, summarize_dataset, validate_feature_dataset
from quant_trading.features.volatility import build_volatility_features
from quant_trading.features.volume import build_volume_features
from quant_trading.targets import build_targets
from quant_trading.utils.config import FeatureConfig


@dataclass(frozen=True)
class FeatureDataset:
    data: pd.DataFrame
    feature_columns: tuple[str, ...]
    target_columns: tuple[str, ...]
    metadata: dict[str, FeatureMetadata]
    summary: DatasetSummary


def build_feature_dataset(panel: pd.DataFrame, config: FeatureConfig) -> FeatureDataset:
    validate_input_panel(panel)
    source = panel.copy(deep=True).sort_index()
    if not source.index.equals(panel.index):
        raise ValueError("Input panel must be sorted by (date, ticker)")
    groups = set(config.enabled_groups)
    supported = {"momentum", "mean_reversion", "volatility", "volume", "market"}
    if unknown := groups - supported:
        raise ValueError(f"Unknown enabled feature groups: {sorted(unknown)}")

    metadata = base_metadata(
        config.return_lookbacks, config.moving_average_windows, config.volatility_windows
    )
    blocks: list[pd.DataFrame] = []
    momentum = build_momentum_features(
        source, config.return_lookbacks, config.moving_average_windows
    )
    if "momentum" in groups:
        blocks.append(momentum)
    if "mean_reversion" in groups:
        required = {"ret_1d", "ret_2d", "ret_5d", "price_to_sma_5"}
        if not required.issubset(momentum.columns):
            raise ValueError("Mean reversion requires return lookbacks 1, 2, 5 and SMA window 5")
        blocks.append(build_mean_reversion_features(momentum))
    daily_returns = trailing_returns(source["close"].astype(float), 1)
    if "volatility" in groups:
        if not {5, 20, 60}.issubset(config.volatility_windows):
            raise ValueError("Volatility ratios require windows 5, 20, and 60")
        blocks.append(build_volatility_features(daily_returns, config.volatility_windows))
    if "volume" in groups:
        blocks.append(build_volume_features(source))
    if "market" in groups:
        blocks.append(build_market_features(source, daily_returns, config.market_benchmark))
    raw_features = pd.concat(blocks, axis=1)
    if raw_features.columns.duplicated().any():
        raise ValueError("Feature groups produced duplicate columns")

    transformed = apply_cross_sectional_transforms(
        raw_features,
        config.cross_sectional_features,
        config.cross_sectional_transforms,
        min_observations=config.min_cross_sectional_observations,
    )
    for name in transformed.columns:
        source_name = name.removesuffix("_rank").removesuffix("_cs_zscore")
        suffix = "rank" if name.endswith("_rank") else "cs_zscore"
        metadata[name] = transformed_metadata(metadata[source_name], suffix)
    features = pd.concat([raw_features, transformed], axis=1)
    targets = build_targets(
        source,
        config.target_horizons,
        benchmark=config.market_benchmark,
        rank_horizons=config.rank_target_horizons,
        excess_horizons=config.excess_target_horizons,
        min_cross_sectional_observations=config.min_cross_sectional_observations,
    )
    dataset = pd.concat([features, targets], axis=1)
    feature_columns = tuple(features.columns)
    target_columns = tuple(targets.columns)
    if config.primary_target not in target_columns:
        raise ValueError(f"Primary target {config.primary_target!r} was not built")
    validate_feature_dataset(
        dataset,
        expected_index=source.index,
        feature_columns=feature_columns,
        target_columns=target_columns,
    )
    summary = summarize_dataset(dataset, feature_columns, target_columns, config.primary_target)
    return FeatureDataset(dataset, feature_columns, target_columns, metadata, summary)

