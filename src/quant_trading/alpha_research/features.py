"""Small, hypothesis-driven Phase 3.5 feature set."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _by_ticker(series: pd.Series):
    return series.groupby(level="ticker", sort=False, group_keys=False)


def build_momentum_expansion(panel: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    close = panel["close"].astype(float)
    grouped = _by_ticker(close)
    output = pd.DataFrame(index=panel.index)
    definitions = {
        "momentum_6_1": (126, 21),
        "momentum_9_1": (189, 21),
        "momentum_12_1": (252, 21),
        "momentum_12_2": (252, 42),
    }
    for name, (lookback, skip) in definitions.items():
        output[name] = grouped.shift(skip) / grouped.shift(lookback) - 1.0
    output["risk_adjusted_momentum_12_1"] = (
        output["momentum_12_1"] / existing["realized_vol_60"].replace(0.0, np.nan)
    )
    returns_5 = grouped.pct_change(5, fill_method=None)
    returns_21 = grouped.pct_change(21, fill_method=None)
    output["positive_week_fraction_52"] = (
        _by_ticker(returns_5.gt(0).where(returns_5.notna()).astype(float))
        .rolling(52, min_periods=52).mean().reset_index(level=0, drop=True)
    )
    output["positive_month_fraction_12"] = (
        _by_ticker(returns_21.gt(0).where(returns_21.notna()).astype(float))
        .rolling(12, min_periods=12).mean().reset_index(level=0, drop=True)
    )
    return output


def idiosyncratic_volatility_60(dataset: pd.DataFrame) -> pd.Series:
    asset = dataset["ret_1d"]
    market = dataset["market_return_1d"]
    grouped_asset = _by_ticker(asset)
    grouped_market = _by_ticker(market)
    var_asset = grouped_asset.rolling(60, min_periods=60).var(ddof=0).reset_index(level=0, drop=True)
    var_market = grouped_market.rolling(60, min_periods=60).var(ddof=0).reset_index(level=0, drop=True)
    covariance = (
        _by_ticker(asset * market).rolling(60, min_periods=60).mean().reset_index(level=0, drop=True)
        - grouped_asset.rolling(60, min_periods=60).mean().reset_index(level=0, drop=True)
        * grouped_market.rolling(60, min_periods=60).mean().reset_index(level=0, drop=True)
    )
    residual_variance = (var_asset - covariance.pow(2) / var_market.replace(0.0, np.nan)).clip(lower=0.0)
    return np.sqrt(residual_variance) * np.sqrt(252.0)


def decompose_daily_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Adjusted overnight and intraday returns available after date-t close.

    yfinance ``auto_adjust=True`` applies a common daily adjustment factor to OHLC. The identity is
    validated, but provider revisions remain a limitation. These are diagnostics, not fill prices.
    """
    previous_close = _by_ticker(panel["close"].astype(float)).shift(1)
    overnight = panel["open"].astype(float) / previous_close - 1.0
    intraday = panel["close"].astype(float) / panel["open"].astype(float) - 1.0
    reconstructed = (1.0 + overnight) * (1.0 + intraday) - 1.0
    close_to_close = panel["close"].astype(float) / previous_close - 1.0
    mismatch = (reconstructed - close_to_close).abs().dropna()
    if len(mismatch) and mismatch.max() > 1e-10:
        raise ValueError("Adjusted OHLC return decomposition identity failed")
    return pd.DataFrame({
        "overnight_return_1d": overnight,
        "intraday_return_1d": intraday,
        "overnight_reversal": -overnight,
        "intraday_reversal": -intraday,
    }, index=panel.index)
