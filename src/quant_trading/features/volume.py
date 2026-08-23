"""Volume and approximate liquidity features."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_trading.features.common import by_ticker


def build_volume_features(panel: pd.DataFrame) -> pd.DataFrame:
    volume = panel["volume"].astype(float)
    dollar_volume = panel["close"].astype(float) * volume
    output = pd.DataFrame({"dollar_volume": dollar_volume}, index=panel.index)
    for days in (20, 60):
        mean = by_ticker(dollar_volume).rolling(days, min_periods=days).mean()
        output[f"avg_dollar_volume_{days}"] = mean.reset_index(level=0, drop=True)
    volume_roll = by_ticker(volume).rolling(20, min_periods=20)
    mean_volume = volume_roll.mean().reset_index(level=0, drop=True)
    std_volume = volume_roll.std(ddof=1).reset_index(level=0, drop=True).replace(0.0, np.nan)
    output["relative_volume_20"] = volume / mean_volume.replace(0.0, np.nan)
    output["volume_zscore_20"] = (volume - mean_volume) / std_volume
    return output

