"""Queryable definitions for research features and targets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureMetadata:
    name: str
    category: str
    description: str
    lookback_days: int
    uses_market_data: bool = False
    cross_sectional: bool = False
    formula: str = ""


def base_metadata(
    return_lookbacks: tuple[int, ...],
    moving_average_windows: tuple[int, ...],
    volatility_windows: tuple[int, ...],
) -> dict[str, FeatureMetadata]:
    """Build metadata for configurable raw features."""
    result: dict[str, FeatureMetadata] = {}
    for days in return_lookbacks:
        name = f"ret_{days}d"
        result[name] = FeatureMetadata(
            name, "momentum", f"Trailing {days}-session adjusted-close return.", days,
            formula=f"close[t] / close[t-{days}] - 1",
        )
    for days in moving_average_windows:
        name = f"price_to_sma_{days}"
        result[name] = FeatureMetadata(
            name, "momentum", f"Normalized distance from the {days}-session close SMA.", days,
            formula=f"close[t] / mean(close[t-{days - 1}:t]) - 1",
        )
    result["momentum_12_1"] = FeatureMetadata(
        "momentum_12_1", "momentum", "Approximate 12-month momentum excluding the latest month.",
        252, formula="close[t-21] / close[t-252] - 1",
    )
    for days in (5, 10, 20):
        result[f"return_zscore_{days}"] = FeatureMetadata(
            f"return_zscore_{days}", "mean_reversion",
            f"Current 1-day return versus its trailing {days}-session distribution.", days + 1,
            formula=f"(ret_1d[t] - mean(ret_1d, {days})) / std(ret_1d, {days}, ddof=1)",
        )
    result["short_price_to_sma_5"] = FeatureMetadata(
        "short_price_to_sma_5", "mean_reversion", "Short normalized distance from 5-day SMA.", 5,
        formula="price_to_sma_5",
    )
    for days in volatility_windows:
        result[f"realized_vol_{days}"] = FeatureMetadata(
            f"realized_vol_{days}", "volatility",
            f"Annualized sample standard deviation of 1-day returns over {days} sessions.", days + 1,
            formula=f"std(ret_1d, {days}, ddof=1) * sqrt(252)",
        )
    result.update({
        "downside_vol_20": FeatureMetadata(
            "downside_vol_20", "volatility", "Annualized RMS of negative daily returns; non-negative returns contribute zero.", 21,
            formula="sqrt(mean(min(ret_1d, 0)^2, 20)) * sqrt(252)",
        ),
        "vol_ratio_5_20": FeatureMetadata("vol_ratio_5_20", "volatility", "5-day divided by 20-day realized volatility.", 21, formula="realized_vol_5 / realized_vol_20"),
        "vol_ratio_20_60": FeatureMetadata("vol_ratio_20_60", "volatility", "20-day divided by 60-day realized volatility.", 61, formula="realized_vol_20 / realized_vol_60"),
        "dollar_volume": FeatureMetadata("dollar_volume", "liquidity", "Adjusted close multiplied by reported share volume.", 1, formula="close * volume"),
        "avg_dollar_volume_20": FeatureMetadata("avg_dollar_volume_20", "liquidity", "20-session mean dollar volume.", 20),
        "avg_dollar_volume_60": FeatureMetadata("avg_dollar_volume_60", "liquidity", "60-session mean dollar volume.", 60),
        "relative_volume_20": FeatureMetadata("relative_volume_20", "liquidity", "Current volume divided by its 20-session mean.", 20),
        "volume_zscore_20": FeatureMetadata("volume_zscore_20", "liquidity", "Current volume z-score within 20 sessions.", 20),
    })
    for name, lookback, description in (
        ("market_return_1d", 2, "SPY 1-day return aligned by date."),
        ("excess_market_return_1d", 2, "Security 1-day return minus SPY return."),
        ("beta_20", 21, "20-return rolling beta to SPY."),
        ("beta_60", 61, "60-return rolling beta to SPY."),
        ("residual_return_1d", 22, "Return minus lagged 20-day beta times market return."),
        ("relative_momentum_20", 21, "20-day security return minus 20-day SPY return."),
        ("relative_momentum_60", 61, "60-day security return minus 60-day SPY return."),
    ):
        result[name] = FeatureMetadata(name, "market_relative", description, lookback, True)
    return result


def transformed_metadata(source: FeatureMetadata, suffix: str) -> FeatureMetadata:
    kind = "percentile rank" if suffix == "rank" else "cross-sectional z-score"
    return FeatureMetadata(
        f"{source.name}_{suffix}", source.category, f"Daily {kind} of {source.name}.",
        source.lookback_days, source.uses_market_data, True,
        f"{kind} across non-missing securities on date t",
    )

