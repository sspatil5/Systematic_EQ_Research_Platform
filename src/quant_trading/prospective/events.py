"""Strict two-stage prospective signal and hypothetical execution events."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import pandas as pd

from quant_trading.prospective.storage import ArtifactStore, sha256_file

SIGNAL_COLUMNS = ["momentum_12_1", "sector_neutral_momentum_12_1",
                  "residual_volatility_beta", "combined_momentum_volatility"]


def validate_signal_timing(signal_date, max_input_date):
    if pd.Timestamp(max_input_date) > pd.Timestamp(signal_date):
        raise ValueError("Future-dated input detected; prospective run is invalid")


def validate_benchmark_alignment(strategy_dates, benchmark_dates):
    if not pd.DatetimeIndex(strategy_dates).equals(pd.DatetimeIndex(benchmark_dates)):
        raise ValueError("Prospective strategy and benchmark observation periods differ")


def eligible_universe(universe: pd.DataFrame, rules) -> pd.DataFrame:
    required = {"ticker", "security_id", "exchange", "security_type", "sector", "price",
                "avg_dollar_volume_20", "history_sessions"}
    missing = required - set(universe.columns)
    if missing: raise ValueError(f"Universe snapshot missing fields: {sorted(missing)}")
    valid = (
        universe.exchange.isin(rules.allowed_exchanges)
        & universe.security_type.isin(rules.security_types)
        & (universe.price >= rules.minimum_price)
        & (universe.avg_dollar_volume_20 >= rules.minimum_trailing_dollar_volume)
        & (universe.history_sessions >= rules.minimum_history_sessions)
        & (universe.sector.notna() if rules.sector_required else True)
    )
    out = universe.copy(); out["eligibility"] = valid
    out["ineligibility_reason"] = ""
    out.loc[~valid, "ineligibility_reason"] = "FAILED_FROZEN_UNIVERSE_RULE"
    return out


def stage_a(store: ArtifactStore, config, signal_date, universe, market_data, signals,
            current_shares: dict[str, dict[str, float]] | None = None,
            account_equity: dict[str, float] | None = None):
    date_token = pd.Timestamp(signal_date).strftime("%Y_%m_%d")
    maximum = pd.to_datetime(market_data["date"]).max()
    validate_signal_timing(signal_date, maximum)
    if set(SIGNAL_COLUMNS) - set(signals.columns):
        raise ValueError("Frozen signal inputs are incomplete")
    snapshot = eligible_universe(universe, config.universe)
    valid = snapshot.loc[snapshot.eligibility, "ticker"]
    signal_snapshot = snapshot[["ticker", "security_id", "sector", "eligibility", "ineligibility_reason"]].merge(
        signals[["ticker", *SIGNAL_COLUMNS]], on="ticker", how="left"
    )
    signal_snapshot.insert(0, "signal_date", str(pd.Timestamp(signal_date).date()))
    signal_snapshot.insert(1, "calculation_timestamp", datetime.now(timezone.utc).isoformat())
    signal_snapshot["primary_rank"] = signal_snapshot.loc[signal_snapshot.ticker.isin(valid), "sector_neutral_momentum_12_1"].rank(method="first", ascending=False)
    signal_snapshot["challenger_rank"] = signal_snapshot.loc[signal_snapshot.ticker.isin(valid), "combined_momentum_volatility"].rank(method="first", ascending=False)
    current_shares = current_shares or {}; account_equity = account_equity or {}
    files = []
    files.append(store.write_frame(f"universe/universe_{date_token}.parquet", snapshot, "UNIVERSE_SNAPSHOT", maximum))
    files.append(store.write_frame(f"market_data/market_{date_token}.parquet", market_data, "DATA_SNAPSHOT", maximum))
    files.append(store.write_frame(f"signals/signals_{date_token}.parquet", signal_snapshot, "SIGNAL_SNAPSHOT", maximum))
    for account, column in (("primary", "sector_neutral_momentum_12_1"),
                            ("challenger", "combined_momentum_volatility"),
                            ("raw_momentum", "momentum_12_1")):
        selected = signal_snapshot.query("eligibility").dropna(subset=[column]).nlargest(config.portfolio.size, column).copy()
        selected["rank"] = range(1, len(selected) + 1); selected["target_weight"] = 1 / len(selected) if len(selected) else 0
        selected["hypothetical_target_dollars"] = account_equity.get(account, config.portfolio.initial_equity) * selected.target_weight
        target = selected[["signal_date", "ticker", column, "rank", "sector", "target_weight", "hypothetical_target_dollars"]].rename(columns={column:"signal_score"})
        orders = target[["signal_date", "ticker", "target_weight"]].copy()
        orders.insert(0, "experiment_id", config.experiment_id)
        orders.insert(2, "creation_timestamp", datetime.now(timezone.utc).isoformat())
        orders["expected_execution_date"] = "NEXT_VALID_SESSION"
        account_shares = current_shares.get(account, {})
        orders["side"] = orders.ticker.map(lambda t: "BUY" if account_shares.get(t, 0) == 0 else "RESIZE")
        orders["current_shadow_shares"] = orders.ticker.map(account_shares).fillna(0)
        orders["desired_notional"] = target.hypothetical_target_dollars.to_numpy()
        orders["reason"] = orders.side.map({"BUY":"ENTER", "RESIZE":"REBALANCE"})
        exits = sorted(set(account_shares) - set(selected.ticker))
        if exits:
            exit_orders = pd.DataFrame({
                "experiment_id":config.experiment_id, "signal_date":str(pd.Timestamp(signal_date).date()),
                "creation_timestamp":datetime.now(timezone.utc).isoformat(),
                "expected_execution_date":"NEXT_VALID_SESSION", "ticker":exits, "side":"SELL",
                "target_weight":0.0, "current_shadow_shares":[account_shares[t] for t in exits],
                "desired_notional":0.0, "reason":"EXIT",
            })
            orders = pd.concat([orders, exit_orders], ignore_index=True)
        assert "execution_price" not in orders and "observed_open" not in orders
        files.append(store.write_frame(f"targets/{account}_{date_token}.parquet", target, "TARGET_SNAPSHOT", maximum))
        files.append(store.write_frame(f"orders/{account}_{date_token}.parquet", orders, "ORDERS_FROZEN", maximum))
    store.audit("SIGNAL_GENERATED", signal_date, "prospective-signal", "SUCCESS", files)
    return files


def stage_b(store: ArtifactStore, config, account, signal_date, execution_date, opens,
            cash, positions, cost_bps=None):
    token = pd.Timestamp(signal_date).strftime("%Y_%m_%d")
    orders_path = store.root / f"orders/{account}_{token}.parquet"
    if not orders_path.exists(): raise FileNotFoundError("Frozen Stage A orders do not exist")
    execution_token = pd.Timestamp(execution_date).strftime("%Y_%m_%d")
    destination = f"executions/{account}_{token}_to_{execution_token}.parquet"
    if (store.root / destination).exists(): raise FileExistsError("Execution already captured")
    orders = pd.read_parquet(orders_path); positions = dict(positions); bps = config.execution.cost_bps if cost_bps is None else cost_bps
    rows = []
    for order in orders.itertuples(index=False):
        quote = opens.loc[opens.ticker.eq(order.ticker), "open"]
        if quote.empty or not pd.notna(quote.iloc[0]) or quote.iloc[0] <= 0:
            rows.append({"signal_date": order.signal_date, "execution_date": execution_date,
                         "ticker": order.ticker, "status":"SKIPPED_MISSING_OPEN"})
            continue
        price = float(quote.iloc[0]); target = math.floor(float(order.desired_notional) / price)
        pre = positions.get(order.ticker, 0); delta = target - pre
        if delta > 0:
            affordable = math.floor(cash / (price * (1 + bps / 10_000)))
            delta = min(delta, affordable)
        notional = abs(delta) * price; cost = notional * bps / 10_000
        cash += (notional - cost) if delta < 0 else -(notional + cost)
        positions[order.ticker] = pre + delta
        rows.append({"signal_date": order.signal_date, "execution_date": execution_date,
            "execution_timestamp": datetime.now(timezone.utc).isoformat(), "ticker": order.ticker,
            "side": "BUY" if delta > 0 else "SELL" if delta < 0 else "UNCHANGED", "shares": abs(delta),
            "observed_open": price, "assumed_slippage_bps": bps, "estimated_cost": cost,
            "trade_notional": notional, "pre_trade_shares": pre, "post_trade_shares": pre + delta,
            "cash_after": cash, "status":"EXECUTED" if delta else "UNCHANGED",
            "orders_sha256": sha256_file(orders_path)})
    frame = pd.DataFrame(rows)
    path = store.write_frame(destination, frame, "EXECUTION_CAPTURED", execution_date)
    state = {"experiment_id":config.experiment_id, "account":account, "as_of":str(execution_date),
             "cash":cash, "positions":positions, "cumulative_costs":float(frame.get("estimated_cost", pd.Series(dtype=float)).sum())}
    state_path = store.write_json(f"account/{account}_{execution_token}.json", state, "ACCOUNT_STATE")
    store.audit("EXECUTION_CAPTURED", signal_date, "prospective-execute", "SUCCESS", (path, state_path))
    return state, frame


def parallel_cost_accounting(executions: pd.DataFrame, scenarios=(0, 2, 5, 10, 20)) -> pd.DataFrame:
    """Apply alternate costs to identical observed shares/notional; never change trade decisions."""
    base = executions.loc[executions.status.eq("EXECUTED")].copy()
    rows = []
    for bps in scenarios:
        scenario = base[["signal_date", "execution_date", "ticker", "side", "shares", "trade_notional"]].copy()
        scenario["cost_bps"] = bps
        scenario["estimated_cost"] = scenario.trade_notional.abs() * bps / 10_000
        rows.append(scenario)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
