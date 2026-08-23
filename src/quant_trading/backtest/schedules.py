"""Deterministic signal-date schedules."""

from __future__ import annotations

import pandas as pd


def signal_dates(dates: pd.DatetimeIndex, frequency: str) -> pd.DatetimeIndex:
    dates = pd.DatetimeIndex(dates).sort_values().unique()
    if frequency == "daily":
        return dates
    if frequency == "10_sessions":
        return dates[::10]
    series = pd.Series(dates, index=dates)
    if frequency == "weekly":
        return pd.DatetimeIndex(series.groupby(dates.to_period("W-FRI")).last().to_numpy())
    if frequency == "monthly":
        return pd.DatetimeIndex(series.groupby(dates.to_period("M")).last().to_numpy())
    raise ValueError(f"Unknown frequency {frequency!r}")

