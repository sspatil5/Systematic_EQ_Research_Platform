"""Shared point-in-time panel helpers."""

from __future__ import annotations

import pandas as pd


def validate_input_panel(panel: pd.DataFrame) -> None:
    if not isinstance(panel.index, pd.MultiIndex) or panel.index.names != ["date", "ticker"]:
        raise ValueError("Input must use a (date, ticker) MultiIndex")
    if panel.index.has_duplicates:
        raise ValueError("Input contains duplicate (date, ticker) rows")
    missing = {"close", "volume"} - set(panel.columns)
    if missing:
        raise ValueError(f"Input is missing columns: {sorted(missing)}")
    dates = panel.index.get_level_values("date")
    if not isinstance(dates, pd.DatetimeIndex) or dates.isna().any():
        raise ValueError("date index must contain valid pandas timestamps")


def by_ticker(series: pd.Series):
    return series.groupby(level="ticker", sort=False, group_keys=False)


def trailing_returns(close: pd.Series, days: int) -> pd.Series:
    return by_ticker(close).pct_change(periods=days, fill_method=None)

