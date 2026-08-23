import numpy as np
import pandas as pd
import pytest

from quant_trading.analysis.performance import benchmark_returns
from quant_trading.backtest.costs import transaction_cost
from quant_trading.backtest.engine import BacktestConfig, run_backtest
from quant_trading.backtest.execution import execution_instruction
from quant_trading.backtest.schedules import signal_dates
from quant_trading.portfolio.ranking import validate_signal
from quant_trading.portfolio.sizing import target_shares


def _inputs(days=8, tickers=("A", "B", "SPY"), rising=True):
    dates = pd.bdate_range("2022-01-03", periods=days)
    index = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    frame = pd.DataFrame(index=index)
    day = np.repeat(np.arange(days), len(tickers))
    base = np.tile(np.arange(len(tickers)) * 10 + 10.0, days)
    frame["open"] = base + (day if rising else 0)
    frame["close"] = frame.open + 1
    frame["high"] = frame.close + 1
    frame["low"] = frame.open - 1
    frame["volume"] = 10_000_000
    signals = pd.DataFrame(index=index)
    signals["sector_neutral_momentum_12_1"] = np.tile(np.arange(len(tickers), 0, -1), days)
    signals["combined_momentum_volatility"] = signals.sector_neutral_momentum_12_1
    signals["momentum_12_1"] = signals.sector_neutral_momentum_12_1
    signals["avg_dollar_volume_20"] = 100_000_000.0
    sectors = pd.Series("Sector", index=index)
    return frame, signals, sectors, dates


def _run(**kwargs):
    panel, signals, sectors, _ = _inputs()
    config = BacktestConfig(signal="sector_neutral_momentum_12_1", liquidity_floor=0, **kwargs)
    return run_backtest(panel, signals, sectors, config)


def test_signal_date_executes_at_next_open():
    _, _, _, dates = _inputs()
    instruction = execution_instruction(dates, dates[2], "next_open")
    assert instruction.signal_date == dates[2]
    assert instruction.execution_date == dates[3]
    assert instruction.price_column == "open"


def test_execution_delay_modes():
    _, _, _, dates = _inputs()
    assert execution_instruction(dates, dates[1], "next_close").execution_date == dates[2]
    assert execution_instruction(dates, dates[1], "second_open").execution_date == dates[3]


def test_whole_share_sizing_uses_execution_price():
    assert target_shares(30_000, 101, 10, fractional_shares=False) == 29


def test_transaction_cost_is_explicit_and_exact():
    assert transaction_cost(10_000, 5) == pytest.approx(5.0)


def test_engine_uses_next_open_and_prior_signal():
    result = _run(frequency="daily", top_n=1, cost_bps=0)
    first = result.trades.iloc[0]
    assert first.execution_date > first.signal_date
    panel, _, _, _ = _inputs()
    assert first.execution_price == panel.loc[(first.execution_date, first.ticker), "open"]


def test_engine_has_whole_shares_and_no_leverage():
    result = _run(frequency="daily", top_n=2, cost_bps=5)
    assert (result.trades.shares % 1 == 0).all()
    assert result.daily.cash.min() >= -1e-8
    assert result.daily.gross_exposure.max() <= 1 + 1e-8


def test_cash_reconciles_with_trade_ledger():
    result = _run(frequency="daily", top_n=1, cost_bps=5)
    buys = result.trades.query("side == 'BUY'")
    sells = result.trades.query("side == 'SELL'")
    expected = 30_000 - buys.trade_notional.sum() - buys.estimated_cost.sum()
    expected += sells.trade_notional.sum() - sells.estimated_cost.sum()
    assert result.daily.cash.iloc[-1] == pytest.approx(expected)


def test_turnover_is_nonnegative_and_only_on_trade_days():
    result = _run(frequency="weekly", top_n=1, cost_bps=0)
    assert (result.daily.turnover >= 0).all()
    trade_dates = set(result.trades.execution_date)
    assert set(result.daily.index[result.daily.turnover > 0]) <= trade_dates


def test_holdings_preserve_scores_and_ranks():
    result = _run(frequency="daily", top_n=2, cost_bps=0)
    assert result.holdings.signal_score.notna().all()
    assert result.holdings["rank"].between(1, 2).all()


def test_adjusted_price_series_has_no_artificial_split_loss():
    panel, signals, sectors, dates = _inputs(days=5, tickers=("A",), rising=False)
    panel.loc[:, ["open", "close"]] = 50.0
    panel.loc[:, "high"] = 51.0; panel.loc[:, "low"] = 49.0
    result = run_backtest(panel, signals, sectors, BacktestConfig(
        signal="sector_neutral_momentum_12_1", frequency="daily", top_n=1,
        cost_bps=0, liquidity_floor=0,
    ))
    assert result.daily.equity.loc[dates[1]:].nunique() == 1


def test_only_frozen_signals_are_accepted():
    with pytest.raises(ValueError):
        validate_signal("new_optimized_signal")


def test_schedule_uses_observed_sessions():
    _, _, _, dates = _inputs(15)
    weekly = signal_dates(dates, "weekly")
    assert all(date in dates for date in weekly)
    assert len(signal_dates(dates, "10_sessions")) == 2


def test_benchmark_returns_use_spy_and_lagged_liquidity():
    panel, signals, _, dates = _inputs()
    result = benchmark_returns(panel, signals, liquidity_floor=0)
    expected = panel.xs("SPY", level="ticker").close.pct_change().fillna(0)
    pd.testing.assert_series_equal(result.spy, expected, check_names=False)
    assert result.index.equals(dates)


def test_higher_cost_cannot_improve_same_trade_path():
    free = _run(frequency="weekly", top_n=1, cost_bps=0)
    costly = _run(frequency="weekly", top_n=1, cost_bps=20)
    assert costly.daily.equity.iloc[-1] <= free.daily.equity.iloc[-1]


def test_scramble_is_reproducible_and_changes_selection():
    a = _run(frequency="daily", top_n=1, cost_bps=0, random_seed=7, scramble_signal=True)
    b = _run(frequency="daily", top_n=1, cost_bps=0, random_seed=7, scramble_signal=True)
    base = _run(frequency="daily", top_n=1, cost_bps=0)
    assert a.holdings.ticker.tolist() == b.holdings.ticker.tolist()
    assert a.holdings.ticker.tolist() != base.holdings.ticker.tolist()


def test_random_portfolio_is_reproducible():
    a = _run(frequency="daily", top_n=1, cost_bps=0, random_seed=9)
    b = _run(frequency="daily", top_n=1, cost_bps=0, random_seed=9)
    assert a.holdings.ticker.tolist() == b.holdings.ticker.tolist()


def test_missing_quote_carries_last_close_and_defers_trade():
    panel, signals, sectors, dates = _inputs(days=6, tickers=("A", "B"))
    panel = panel.drop(index=(dates[3], "A"))
    signals = signals.drop(index=(dates[3], "A"))
    sectors = sectors.drop(index=(dates[3], "A"))
    result = run_backtest(panel, signals, sectors, BacktestConfig(
        signal="sector_neutral_momentum_12_1", frequency="daily", top_n=1,
        cost_bps=0, liquidity_floor=0,
    ))
    assert result.daily.equity.notna().all()
    assert not ((result.trades.execution_date == dates[3]) & (result.trades.ticker == "A")).any()
