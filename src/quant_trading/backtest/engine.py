"""Whole-share, long-only, next-session execution backtest engine."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np
import pandas as pd

from quant_trading.backtest.costs import transaction_cost
from quant_trading.backtest.execution import execution_instruction
from quant_trading.backtest.schedules import signal_dates
from quant_trading.portfolio.constructor import construct_targets
from quant_trading.portfolio.ranking import select_top, validate_signal


@dataclass(frozen=True)
class BacktestConfig:
    signal: str
    top_n: int = 10
    frequency: str = "weekly"
    execution_mode: str = "next_open"
    cost_bps: float = 5.0
    initial_cash: float = 30_000.0
    liquidity_floor: float = 20_000_000.0
    fractional_shares: bool = False
    random_seed: int | None = None
    scramble_signal: bool = False
    record_details: bool = True


@dataclass
class BacktestResult:
    config: BacktestConfig
    daily: pd.DataFrame
    trades: pd.DataFrame
    holdings: pd.DataFrame
    sector_exposures: pd.DataFrame
    contributions: pd.Series
    active_start: pd.Timestamp | None


def validate_open_prices(panel: pd.DataFrame) -> dict[str, float | int]:
    prices = panel[["open", "high", "low", "close"]]
    nonpositive = int((prices["open"] <= 0).sum())
    tolerance = 1e-10 * prices.abs().max(axis=1)
    outside = int(((prices.open + tolerance < prices.low) | (prices.open - tolerance > prices.high)).sum())
    previous = panel["close"].groupby(level="ticker").shift(1)
    overnight = panel["open"] / previous - 1.0
    suspicious = int((overnight.abs() > 0.50).sum())
    missing = int(panel["open"].isna().sum())
    return {
        "nonpositive_opens": nonpositive, "opens_outside_bar": outside,
        "missing_opens": missing, "overnight_moves_over_50pct": suspicious,
        "maximum_absolute_overnight_return": float(overnight.abs().max()),
    }


def run_backtest(
    panel: pd.DataFrame,
    signals: pd.DataFrame,
    sectors: pd.Series,
    config: BacktestConfig,
) -> BacktestResult:
    validate_signal(config.signal)
    if config.top_n <= 0 or config.initial_cash <= 0:
        raise ValueError("Portfolio size and initial cash must be positive")
    dates = panel.index.get_level_values("date").unique().sort_values()
    schedule = signal_dates(dates, config.frequency)
    instructions: dict[pd.Timestamp, list] = {}
    for signal_date in schedule:
        instruction = execution_instruction(dates, signal_date, config.execution_mode)
        if instruction is not None:
            instructions.setdefault(instruction.execution_date, []).append(instruction)

    cash = config.initial_cash
    positions: dict[str, float] = {}
    average_cost: dict[str, float] = {}
    realized_pnl = 0.0
    total_costs = 0.0
    rng = np.random.default_rng(config.random_seed)
    trade_rows: list[dict[str, object]] = []
    holding_rows: list[dict[str, object]] = []
    daily_rows: list[dict[str, object]] = []
    sector_rows: list[dict[str, object]] = []
    contributions: dict[str, float] = {}
    previous_close: pd.Series | None = None
    last_close: dict[str, float] = {}
    previous_positions: dict[str, float] = {}
    active_start: pd.Timestamp | None = None

    for date in dates:
        market = panel.xs(date, level="date")
        close_prices = market["close"].astype(float)
        daily_cost = daily_notional = 0.0
        pretrade_equity_for_turnover = np.nan
        executed_signal_date: pd.Timestamp | None = None

        if date in instructions:
            # At most one instruction exists for predefined schedules; process deterministically.
            instruction = instructions[date][-1]
            executed_signal_date = instruction.signal_date
            price_column = instruction.price_column
            execution_prices = market[price_column].astype(float)
            held_value = sum(
                shares * float(execution_prices.get(ticker, np.nan))
                for ticker, shares in positions.items()
                if pd.notna(execution_prices.get(ticker, np.nan))
            )
            pretrade_equity_for_turnover = cash + held_value
            cross = signals.xs(instruction.signal_date, level="date").copy()
            if config.random_seed is not None:
                eligible = cross.dropna(subset=[config.signal, "avg_dollar_volume_20"])
                eligible = eligible[eligible.avg_dollar_volume_20 >= config.liquidity_floor]
                if config.scramble_signal:
                    eligible[config.signal] = rng.permutation(eligible[config.signal].to_numpy())
                    selected = select_top(
                        eligible, config.signal, config.top_n,
                        liquidity_floor=config.liquidity_floor,
                    )
                else:
                    chosen = rng.choice(eligible.index.to_numpy(), size=min(config.top_n, len(eligible)), replace=False)
                    selected = eligible.loc[chosen].copy()
                    selected["rank"] = np.arange(1, len(selected) + 1)
            else:
                selected = select_top(
                    cross, config.signal, config.top_n,
                    liquidity_floor=config.liquidity_floor,
                )
            selected = selected.loc[selected.index.intersection(execution_prices.dropna().index)]
            targets = construct_targets(
                selected, execution_prices, pretrade_equity_for_turnover,
                fractional_shares=config.fractional_shares,
            ) if len(selected) else {}

            # Exits and reductions generate cash before purchases.
            all_tickers = sorted(set(positions) | set(targets))
            differences = {
                ticker: (targets.get(ticker, 0.0) - positions.get(ticker, 0.0))
                if ticker in execution_prices.index and pd.notna(execution_prices.loc[ticker]) else 0.0
                for ticker in all_tickers
            }
            for side_sign in (-1, 1):
                for ticker in all_tickers:
                    difference = differences[ticker]
                    if difference == 0 or int(np.sign(difference)) != side_sign:
                        continue
                    price = float(execution_prices.loc[ticker])
                    pre_position = positions.get(ticker, 0.0)
                    shares = abs(difference)
                    if difference > 0:
                        affordable = cash / (price * (1.0 + config.cost_bps / 10_000.0))
                        if not config.fractional_shares:
                            affordable = math.floor(affordable)
                        shares = min(shares, affordable)
                        if shares <= 0:
                            continue
                    signed_shares = shares if difference > 0 else -shares
                    notional = shares * price
                    cost = transaction_cost(notional, config.cost_bps)
                    if signed_shares > 0:
                        old_cost = average_cost.get(ticker, 0.0) * pre_position
                        cash -= notional + cost
                        positions[ticker] = pre_position + shares
                        average_cost[ticker] = (old_cost + notional) / positions[ticker]
                    else:
                        cash += notional - cost
                        realized_pnl += shares * (price - average_cost.get(ticker, price))
                        positions[ticker] = pre_position - shares
                        if positions[ticker] <= 1e-12:
                            positions.pop(ticker, None); average_cost.pop(ticker, None)
                    total_costs += cost; daily_cost += cost; daily_notional += notional
                    post_position = positions.get(ticker, 0.0)
                    reason = "ENTER" if pre_position == 0 else "EXIT" if post_position == 0 else "RESIZE"
                    trade_rows.append({
                        "signal_date": instruction.signal_date, "order_date": instruction.order_date,
                        "execution_date": date, "ticker": ticker,
                        "side": "BUY" if signed_shares > 0 else "SELL", "shares": shares,
                        "execution_price": price, "trade_notional": notional,
                        "estimated_cost": cost, "pre_trade_position": pre_position,
                        "post_trade_position": post_position, "reason": reason,
                    })
            if trade_rows and active_start is None:
                active_start = date

            execution_marks = {
                ticker: float(execution_prices.loc[ticker])
                if ticker in execution_prices.index and pd.notna(execution_prices.loc[ticker])
                else last_close.get(ticker, average_cost.get(ticker, 0.0))
                for ticker in positions
            }
            post_equity_at_execution = cash + sum(
                shares * execution_marks[ticker] for ticker, shares in positions.items()
            )
            if config.record_details:
                for ticker, shares in positions.items():
                    price = execution_marks[ticker]
                    score = float(selected.loc[ticker, config.signal]) if ticker in selected.index else np.nan
                    rank = int(selected.loc[ticker, "rank"]) if ticker in selected.index else np.nan
                    value = shares * price
                    holding_rows.append({
                        "signal_date": instruction.signal_date, "execution_date": date,
                        "ticker": ticker, "signal_score": score, "rank": rank,
                        "target_weight": 1.0 / len(selected) if len(selected) else 0.0,
                        "shares": shares, "execution_price": price, "position_value": value,
                        "actual_weight": value / post_equity_at_execution if post_equity_at_execution else np.nan,
                        "sector": sectors.loc[(date, ticker)] if (date, ticker) in sectors.index else "Unknown",
                    })

        last_close.update(close_prices.dropna().astype(float).to_dict())
        position_prices = {
            ticker: float(close_prices.loc[ticker]) if ticker in close_prices.index and pd.notna(close_prices.loc[ticker])
            else last_close.get(ticker, average_cost.get(ticker, 0.0))
            for ticker in positions
        }
        equity = cash + sum(shares * position_prices[ticker] for ticker, shares in positions.items())
        market_value = equity - cash
        unrealized = sum(
            shares * (position_prices[ticker] - average_cost.get(ticker, position_prices[ticker]))
            for ticker, shares in positions.items()
        )
        turnover = daily_notional / pretrade_equity_for_turnover if pd.notna(pretrade_equity_for_turnover) and pretrade_equity_for_turnover > 0 else 0.0

        if config.record_details and previous_close is not None:
            for ticker in set(previous_positions) | set(positions):
                if ticker not in close_prices.index or ticker not in previous_close.index:
                    continue
                old_shares = previous_positions.get(ticker, 0.0)
                new_shares = positions.get(ticker, 0.0)
                if executed_signal_date is not None and config.execution_mode.endswith("open"):
                    open_price = float(market.loc[ticker, "open"])
                    pnl = old_shares * (open_price - float(previous_close.loc[ticker])) + new_shares * (float(close_prices.loc[ticker]) - open_price)
                else:
                    pnl = old_shares * (float(close_prices.loc[ticker]) - float(previous_close.loc[ticker]))
                contributions[ticker] = contributions.get(ticker, 0.0) + pnl

        daily_rows.append({
            "date": date, "cash": cash, "market_value": market_value, "equity": equity,
            "realized_pnl": realized_pnl, "unrealized_pnl": unrealized,
            "daily_cost": daily_cost, "cumulative_cost": total_costs,
            "trade_notional": daily_notional, "turnover": turnover,
            "cash_weight": cash / equity if equity else np.nan,
            "gross_exposure": market_value / equity if equity else np.nan,
        })
        if config.record_details and equity > 0 and positions:
            weights = pd.Series({ticker: shares * position_prices[ticker] / equity for ticker, shares in positions.items()})
            sector_values: dict[str, float] = {}
            for ticker, weight in weights.items():
                sector = sectors.loc[(date, ticker)] if (date, ticker) in sectors.index else "Unknown"
                sector_values[sector] = sector_values.get(sector, 0.0) + float(weight)
            for sector, weight in sector_values.items():
                sector_rows.append({"date": date, "sector": sector, "weight": weight})
            daily_rows[-1].update({
                "largest_position": float(weights.max()),
                "top5_concentration": float(weights.nlargest(5).sum()),
                "position_hhi": float(weights.pow(2).sum()),
                "effective_positions": float(1.0 / weights.pow(2).sum()),
                "largest_sector": max(sector_values.values()),
            })
        elif config.record_details:
            daily_rows[-1].update({
                "largest_position": 0.0, "top5_concentration": 0.0,
                "position_hhi": 0.0, "effective_positions": 0.0, "largest_sector": 0.0,
            })
        previous_close = close_prices
        previous_positions = positions.copy()

    daily = pd.DataFrame(daily_rows).set_index("date")
    daily["net_return"] = daily["equity"].pct_change(fill_method=None).fillna(0.0)
    # Gross return adds explicit costs back to the ending equity numerator.
    previous_equity = daily["equity"].shift(1)
    daily["gross_return"] = ((daily["equity"] + daily["daily_cost"]) / previous_equity - 1.0).fillna(0.0)
    return BacktestResult(
        config, daily, pd.DataFrame(trade_rows), pd.DataFrame(holding_rows),
        pd.DataFrame(sector_rows), pd.Series(contributions, name="pnl_contribution").sort_values(),
        active_start,
    )
