"""Performance and drawdown metrics for daily equity curves."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252.0


def drawdown_series(equity: pd.Series) -> pd.Series:
    return equity / equity.cummax() - 1.0


def drawdown_episodes(equity: pd.Series, limit: int = 5) -> pd.DataFrame:
    drawdown = drawdown_series(equity)
    episodes = []
    underwater = False
    start = None
    for date, value in drawdown.items():
        if value < 0 and not underwater:
            underwater = True; start = date
        if underwater and (value == 0 or date == drawdown.index[-1]):
            segment = drawdown.loc[start:date]
            trough = segment.idxmin()
            recovered = date if value == 0 else pd.NaT
            episodes.append({
                "start": start, "trough": trough, "recovery": recovered,
                "max_drawdown": float(segment.min()),
                "duration_days": int((date - start).days),
            })
            underwater = False
    return pd.DataFrame(episodes).sort_values("max_drawdown").head(limit) if episodes else pd.DataFrame()


def performance_metrics(
    returns: pd.Series,
    equity: pd.Series,
    spy_returns: pd.Series,
    *,
    cash_weight: pd.Series | None = None,
    turnover: pd.Series | None = None,
    total_costs: float = 0.0,
    trade_count: int = 0,
) -> dict[str, float | int | str]:
    aligned = pd.concat([returns.rename("strategy"), spy_returns.rename("spy")], axis=1).dropna()
    r = aligned.strategy
    years = max(len(r) / TRADING_DAYS, 1 / TRADING_DAYS)
    total_return = float((1 + r).prod() - 1)
    cagr = float((1 + total_return) ** (1 / years) - 1) if 1 + total_return > 0 else -1.0
    volatility = float(r.std(ddof=1) * np.sqrt(TRADING_DAYS))
    sharpe = float(r.mean() / r.std(ddof=1) * np.sqrt(TRADING_DAYS)) if r.std(ddof=1) > 0 else np.nan
    downside = r[r < 0].std(ddof=1)
    sortino = float(r.mean() / downside * np.sqrt(TRADING_DAYS)) if pd.notna(downside) and downside > 0 else np.nan
    dd = drawdown_series(equity.loc[r.index])
    max_dd = float(dd.min())
    monthly = (1 + r).groupby(r.index.to_period("M")).prod() - 1
    covariance = aligned.cov().loc["strategy", "spy"]
    spy_variance = aligned.spy.var(ddof=1)
    beta = float(covariance / spy_variance) if spy_variance > 0 else np.nan
    correlation = float(aligned.strategy.corr(aligned.spy))
    excess = aligned.strategy - aligned.spy
    tracking_error = float(excess.std(ddof=1) * np.sqrt(TRADING_DAYS))
    information_ratio = float(excess.mean() / excess.std(ddof=1) * np.sqrt(TRADING_DAYS)) if excess.std(ddof=1) > 0 else np.nan
    return {
        "start": str(r.index.min().date()), "end": str(r.index.max().date()),
        "observations": len(r), "total_return": total_return, "cagr": cagr,
        "annualized_return": float(r.mean() * TRADING_DAYS),
        "annualized_volatility": volatility, "zero_rate_sharpe": sharpe,
        "sortino": sortino, "max_drawdown": max_dd,
        "calmar": cagr / abs(max_dd) if max_dd < 0 else np.nan,
        "best_month": float(monthly.max()), "worst_month": float(monthly.min()),
        "positive_month_pct": float((monthly > 0).mean()), "beta_to_spy": beta,
        "correlation_spy": correlation, "tracking_error": tracking_error,
        "information_ratio": information_ratio,
        "average_cash_pct": float(cash_weight.loc[r.index].mean()) if cash_weight is not None else np.nan,
        "annual_turnover": float(turnover.loc[r.index].sum() / years) if turnover is not None else np.nan,
        "average_rebalance_turnover": float(turnover.loc[r.index][turnover.loc[r.index] > 0].mean()) if turnover is not None and (turnover.loc[r.index] > 0).any() else 0.0,
        "estimated_costs": total_costs, "number_of_trades": trade_count,
    }

