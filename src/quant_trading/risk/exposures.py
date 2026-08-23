"""Backward-looking rolling beta and sector exposure summaries."""

import pandas as pd


def rolling_beta(strategy_returns: pd.Series, spy_returns: pd.Series, window: int = 252) -> pd.Series:
    covariance = strategy_returns.rolling(window, min_periods=60).cov(spy_returns)
    variance = spy_returns.rolling(window, min_periods=60).var()
    return covariance / variance.replace(0.0, pd.NA)


def sector_exposure_summary(exposures: pd.DataFrame) -> pd.DataFrame:
    if exposures.empty:
        return pd.DataFrame()
    pivot = exposures.pivot_table(index="date", columns="sector", values="weight", aggfunc="sum", fill_value=0)
    return pd.DataFrame({"average_weight": pivot.mean(), "maximum_weight": pivot.max()}).reset_index()

