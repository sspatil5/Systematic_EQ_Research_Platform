"""SPY-relative features aligned only on contemporaneously available dates."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_trading.features.common import by_ticker, trailing_returns


def build_market_features(
    panel: pd.DataFrame, daily_returns: pd.Series, benchmark: str = "SPY"
) -> pd.DataFrame:
    tickers = panel.index.get_level_values("ticker")
    if benchmark not in set(tickers):
        raise ValueError(f"Market benchmark {benchmark!r} is absent from the panel")
    benchmark_close = panel.xs(benchmark, level="ticker")["close"].astype(float)
    benchmark_return = benchmark_close.pct_change(fill_method=None).rename("market_return_1d")
    dates = panel.index.get_level_values("date")
    market_aligned = pd.Series(dates.map(benchmark_return), index=panel.index, dtype=float)
    output = pd.DataFrame({"market_return_1d": market_aligned}, index=panel.index)
    output["excess_market_return_1d"] = daily_returns - market_aligned

    for days in (20, 60):
        covariance = (
            (daily_returns * market_aligned).groupby(level="ticker", sort=False)
            .rolling(days, min_periods=days).mean().reset_index(level=0, drop=True)
            - by_ticker(daily_returns).rolling(days, min_periods=days).mean().reset_index(level=0, drop=True)
            * by_ticker(market_aligned).rolling(days, min_periods=days).mean().reset_index(level=0, drop=True)
        )
        variance = by_ticker(market_aligned).rolling(days, min_periods=days).var(ddof=0).reset_index(level=0, drop=True)
        output[f"beta_{days}"] = covariance / variance.replace(0.0, np.nan)

    # Lagging beta ensures the exposure estimate uses returns only through t-1.
    lagged_beta = by_ticker(output["beta_20"]).shift(1)
    output["residual_return_1d"] = daily_returns - lagged_beta * market_aligned
    for days in (20, 60):
        asset_momentum = trailing_returns(panel["close"].astype(float), days)
        market_momentum = benchmark_close.pct_change(days, fill_method=None)
        aligned = pd.Series(dates.map(market_momentum), index=panel.index, dtype=float)
        output[f"relative_momentum_{days}"] = asset_momentum - aligned
    return output

