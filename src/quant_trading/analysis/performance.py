"""Benchmarks, sample splits, and year-by-year summaries."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_trading.risk.metrics import drawdown_series, performance_metrics


def benchmark_returns(
    panel: pd.DataFrame, features: pd.DataFrame, liquidity_floor: float
) -> pd.DataFrame:
    close = panel["close"].astype(float)
    asset_returns = close.groupby(level="ticker").pct_change(fill_method=None)
    liquidity = features["avg_dollar_volume_20"].groupby(level="ticker").shift(1)
    eligible = asset_returns.where(liquidity >= liquidity_floor)
    equal_weight = eligible.groupby(level="date").mean()
    spy = asset_returns.xs("SPY", level="ticker")
    return pd.DataFrame({"spy": spy, "equal_weight": equal_weight}).fillna(0.0)


def sample_summaries(result, benchmarks: pd.DataFrame) -> pd.DataFrame:
    daily = result.daily
    start = result.active_start or daily.index.min()
    masks = {
        "FULL": daily.index >= start,
        "DEVELOPMENT": (daily.index >= start) & (daily.index <= pd.Timestamp("2021-12-31")),
        "CONFIRMATION": daily.index >= pd.Timestamp("2022-01-01"),
    }
    rows = []
    for sample, mask in masks.items():
        subset = daily.loc[mask]
        if subset.empty:
            continue
        costs = float(subset.daily_cost.sum())
        trades = 0 if result.trades.empty else int(result.trades.execution_date.isin(subset.index).sum())
        metrics = performance_metrics(
            subset.net_return, subset.equity, benchmarks.spy,
            cash_weight=subset.cash_weight, turnover=subset.turnover,
            total_costs=costs, trade_count=trades,
        )
        spy_total = float((1 + benchmarks.loc[subset.index, "spy"]).prod() - 1)
        ew_total = float((1 + benchmarks.loc[subset.index, "equal_weight"]).prod() - 1)
        years = len(subset) / 252
        metrics.update({
            "sample": sample,
            # Normalize each reported subsample to the configured starting capital.
            "ending_equity": float(result.config.initial_cash * (1 + metrics["total_return"])),
            "spy_cagr": (1 + spy_total) ** (1 / years) - 1,
            "equal_weight_cagr": (1 + ew_total) ** (1 / years) - 1,
        })
        metrics["annualized_excess_spy"] = metrics["cagr"] - metrics["spy_cagr"]
        metrics["annualized_excess_equal_weight"] = metrics["cagr"] - metrics["equal_weight_cagr"]
        rows.append(metrics)
    return pd.DataFrame(rows)


def yearly_summary(result, benchmarks: pd.DataFrame) -> pd.DataFrame:
    rows = []
    daily = result.daily
    for year, subset in daily.groupby(daily.index.year):
        r = subset.net_return
        spy = benchmarks.loc[subset.index, "spy"]
        strategy_return = float((1 + r).prod() - 1)
        spy_return = float((1 + spy).prod() - 1)
        rows.append({
            "year": year, "strategy_return": strategy_return, "spy_return": spy_return,
            "excess_return": strategy_return - spy_return,
            "volatility": float(r.std(ddof=1) * np.sqrt(252)),
            "sharpe": float(r.mean() / r.std(ddof=1) * np.sqrt(252)) if r.std(ddof=1) > 0 else np.nan,
            "max_drawdown": float(drawdown_series((1 + r).cumprod()).min()),
            "turnover": float(subset.turnover.sum()), "costs": float(subset.daily_cost.sum()),
        })
    return pd.DataFrame(rows)
