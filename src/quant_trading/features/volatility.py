"""Backward-looking realized and downside volatility features."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_trading.features.common import by_ticker

ANNUALIZATION_FACTOR = np.sqrt(252.0)


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator / denominator.replace(0.0, np.nan)


def build_volatility_features(
    daily_returns: pd.Series, windows: tuple[int, ...]
) -> pd.DataFrame:
    output = pd.DataFrame(index=daily_returns.index)
    for days in windows:
        std = by_ticker(daily_returns).rolling(days, min_periods=days).std(ddof=1)
        output[f"realized_vol_{days}"] = std.reset_index(level=0, drop=True) * ANNUALIZATION_FACTOR
    downside_squared = daily_returns.clip(upper=0.0).pow(2)
    downside_mean = by_ticker(downside_squared).rolling(20, min_periods=20).mean()
    output["downside_vol_20"] = np.sqrt(downside_mean.reset_index(level=0, drop=True)) * ANNUALIZATION_FACTOR
    output["vol_ratio_5_20"] = _safe_ratio(output["realized_vol_5"], output["realized_vol_20"])
    output["vol_ratio_20_60"] = _safe_ratio(output["realized_vol_20"], output["realized_vol_60"])
    return output

