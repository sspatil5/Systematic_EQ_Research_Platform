"""Translate ranked securities into equal-weight target shares."""

from __future__ import annotations

import pandas as pd

from quant_trading.portfolio.sizing import target_shares


def construct_targets(
    selected: pd.DataFrame,
    execution_prices: pd.Series,
    equity: float,
    *,
    fractional_shares: bool = False,
) -> dict[str, float]:
    count = len(selected)
    return {
        ticker: target_shares(
            equity, float(execution_prices.loc[ticker]), count,
            fractional_shares=fractional_shares,
        )
        for ticker in selected.index
        if ticker in execution_prices.index and pd.notna(execution_prices.loc[ticker])
    }

