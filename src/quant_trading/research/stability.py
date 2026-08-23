"""Temporal stability and signal-decay diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_trading.research.ic import daily_information_coefficients, infer_ic


def period_ic_summary(daily_ic: pd.Series, frequency: str, hac_lags: int) -> pd.DataFrame:
    if daily_ic.empty:
        return pd.DataFrame()
    periods = daily_ic.index.to_period(frequency)
    rows = []
    for period, values in daily_ic.groupby(periods):
        inference = infer_ic(values, hac_lags=hac_lags)
        rows.append({"period": str(period), **inference.to_dict()})
    return pd.DataFrame(rows).set_index("period")


def rolling_ic(daily_ic: pd.Series, windows: tuple[int, ...] = (126, 252)) -> pd.DataFrame:
    return pd.DataFrame({
        f"rolling_{days}d_mean_ic": daily_ic.rolling(days, min_periods=max(20, days // 2)).mean()
        for days in windows
    })


def signal_decay(
    dataset: pd.DataFrame,
    signals: tuple[str, ...],
    horizons: tuple[int, ...],
    minimum_cross_section: int,
) -> pd.DataFrame:
    rows = []
    for signal in signals:
        for horizon in horizons:
            target = f"target_return_{horizon}d"
            ic = daily_information_coefficients(
                dataset, signal, target, minimum_cross_section=minimum_cross_section
            )
            rows.append({
                "signal": signal,
                "horizon": horizon,
                "mean_rank_ic": float(ic["spearman_ic"].mean()) if not ic.empty else np.nan,
                "valid_dates": len(ic),
            })
    return pd.DataFrame(rows)

