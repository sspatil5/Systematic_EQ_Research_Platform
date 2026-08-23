"""Backward-looking adjusted-close momentum features."""

from __future__ import annotations

import pandas as pd

from quant_trading.features.common import by_ticker, trailing_returns


def build_momentum_features(
    panel: pd.DataFrame,
    return_lookbacks: tuple[int, ...],
    moving_average_windows: tuple[int, ...],
) -> pd.DataFrame:
    close = panel["close"].astype(float)
    output = pd.DataFrame(index=panel.index)
    for days in return_lookbacks:
        output[f"ret_{days}d"] = trailing_returns(close, days)
    for days in moving_average_windows:
        sma = by_ticker(close).rolling(days, min_periods=days).mean().reset_index(level=0, drop=True)
        output[f"price_to_sma_{days}"] = close / sma - 1.0
    output["momentum_12_1"] = by_ticker(close).shift(21) / by_ticker(close).shift(252) - 1.0
    return output

