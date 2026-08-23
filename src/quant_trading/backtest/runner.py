"""Frozen Phase 4 experiment orchestration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from quant_trading.alpha_research.runner import build_alpha_dataset
from quant_trading.analysis.attribution import contribution_table, removal_robustness
from quant_trading.analysis.performance import benchmark_returns, sample_summaries, yearly_summary
from quant_trading.backtest.engine import BacktestConfig, validate_open_prices, run_backtest
from quant_trading.risk.exposures import rolling_beta, sector_exposure_summary


def _confirmation_row(result, benchmarks):
    table = sample_summaries(result, benchmarks)
    return table.loc[table["sample"] == "CONFIRMATION"].iloc[0].to_dict()


def run_phase4(panel, features, research_config, alpha_config):
    audit = validate_open_prices(panel)
    if audit["nonpositive_opens"] or audit["opens_outside_bar"] or audit["missing_opens"]:
        raise ValueError(f"Open-price validation failed: {audit}")
    signals, sectors = build_alpha_dataset(panel, features, alpha_config)
    benchmarks = benchmark_returns(panel, features, research_config.liquidity_floor)
    base = BacktestConfig(
        signal=research_config.primary_signal, top_n=research_config.top_n,
        frequency=research_config.rebalance_frequency,
        execution_mode=research_config.execution_mode,
        cost_bps=research_config.primary_cost_bps,
        initial_cash=research_config.initial_cash,
        liquidity_floor=research_config.liquidity_floor,
        fractional_shares=research_config.fractional_shares,
    )
    core_configs = {
        "primary": base,
        "challenger": replace(base, signal=research_config.challenger_signal),
        "raw_momentum_benchmark": replace(base, signal="momentum_12_1"),
    }
    core = {name: run_backtest(panel, signals, sectors, cfg) for name, cfg in core_configs.items()}
    summaries = pd.concat([
        sample_summaries(result, benchmarks).assign(strategy=name)
        for name, result in core.items()
    ], ignore_index=True)
    yearly = pd.concat([
        yearly_summary(result, benchmarks).assign(strategy=name)
        for name, result in core.items()
    ], ignore_index=True)

    sensitivity_rows = []
    experiments = []
    for signal_name, signal in (("primary", research_config.primary_signal),
                                ("challenger", research_config.challenger_signal)):
        for bps in research_config.cost_sensitivity_bps:
            experiments.append(("cost", signal_name, str(bps), replace(base, signal=signal, cost_bps=bps)))
        for delay in research_config.delay_modes:
            experiments.append(("delay", signal_name, delay, replace(base, signal=signal, execution_mode=delay)))
    for n in research_config.top_n_sensitivity:
        experiments.append(("top_n", "primary", str(n), replace(base, top_n=n)))
    for frequency in research_config.frequency_sensitivity:
        experiments.append(("frequency", "primary", frequency, replace(base, frequency=frequency)))
    for kind, strategy, value, cfg in experiments:
        result = run_backtest(panel, signals, sectors, replace(cfg, record_details=False))
        row = _confirmation_row(result, benchmarks)
        sensitivity_rows.append({"test": kind, "strategy": strategy, "value": value, **row})
    sensitivity = pd.DataFrame(sensitivity_rows)

    break_even_rows = []
    for bps in research_config.break_even_cost_bps:
        result = run_backtest(panel, signals, sectors, replace(base, cost_bps=bps, record_details=False))
        break_even_rows.append({"cost_bps": bps, **_confirmation_row(result, benchmarks)})
    break_even = pd.DataFrame(break_even_rows)

    confirm_mask = panel.index.get_level_values("date") >= pd.Timestamp("2022-01-01")
    cp, cs, csec = panel.loc[confirm_mask], signals.loc[confirm_mask], sectors.loc[confirm_mask]
    cb = benchmarks.loc[benchmarks.index >= "2022-01-01"]
    checkpoint = Path(research_config.output_dir) / "randomization_checkpoint.csv"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    if checkpoint.exists():
        random_rows = pd.read_csv(checkpoint).to_dict("records")
    else:
        random_rows = []
    completed = {(int(row["simulation"]), row["kind"]) for row in random_rows}
    for simulation in range(research_config.random_simulations):
        seed = research_config.random_seed + simulation
        for kind, scramble in (("random_selection", False), ("scrambled_signal", True)):
            if (simulation, kind) in completed:
                continue
            result = run_backtest(cp, cs, csec, replace(
                base, random_seed=seed, scramble_signal=scramble, record_details=False
            ))
            row = _confirmation_row(result, cb)
            random_rows.append({"simulation": simulation, "kind": kind, "seed": seed, **row})
            pd.DataFrame(random_rows).to_csv(checkpoint, index=False)
        if simulation % 10 == 9:
            print(f"Completed Phase 4 randomization seed {simulation + 1}/{research_config.random_simulations}", flush=True)
    randomization = pd.DataFrame(random_rows)

    primary = core["primary"]
    challenger = core["challenger"]
    return {
        "open_price_audit": pd.DataFrame([audit]), "benchmarks": benchmarks,
        "core_results": core, "strategy_summary": summaries, "yearly_summary": yearly,
        "sensitivity": sensitivity, "break_even": break_even, "randomization": randomization,
        "primary_contributions": contribution_table(primary),
        "challenger_contributions": contribution_table(challenger),
        "removal_robustness": pd.concat([
            removal_robustness(primary).assign(strategy="primary"),
            removal_robustness(challenger).assign(strategy="challenger")], ignore_index=True),
        "primary_sector_summary": sector_exposure_summary(primary.sector_exposures),
        "challenger_sector_summary": sector_exposure_summary(challenger.sector_exposures),
        "primary_rolling_beta": rolling_beta(primary.daily.net_return, benchmarks.spy),
        "challenger_rolling_beta": rolling_beta(challenger.daily.net_return, benchmarks.spy),
    }


def save_phase4_results(results, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    for name, value in results.items():
        if name == "core_results":
            for strategy, result in value.items():
                result.daily.to_parquet(output / f"{strategy}_daily.parquet")
                result.trades.to_parquet(output / f"{strategy}_trades.parquet", index=False)
                result.holdings.to_parquet(output / f"{strategy}_holdings.parquet", index=False)
                result.sector_exposures.to_parquet(output / f"{strategy}_sector_exposures.parquet", index=False)
        elif isinstance(value, pd.Series):
            value.rename(name).to_csv(output / f"{name}.csv")
        elif isinstance(value, pd.DataFrame):
            value.to_csv(output / f"{name}.csv", index=True if name == "benchmarks" else False)
