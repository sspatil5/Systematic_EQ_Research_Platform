"""Short-horizon mean-reversion features without duplicate return columns."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_trading.features.common import by_ticker


def build_mean_reversion_features(momentum: pd.DataFrame) -> pd.DataFrame:
    """Build z-scores and one named SMA distance; short returns reuse ret_1d/2d/5d."""
    one_day = momentum["ret_1d"]
    output = pd.DataFrame(index=momentum.index)
    for days in (5, 10, 20):
        rolling = by_ticker(one_day).rolling(days, min_periods=days)
        mean = rolling.mean().reset_index(level=0, drop=True)
        std = rolling.std(ddof=1).reset_index(level=0, drop=True).replace(0.0, np.nan)
        output[f"return_zscore_{days}"] = (one_day - mean) / std
    output["short_price_to_sma_5"] = momentum["price_to_sma_5"]
    return output

