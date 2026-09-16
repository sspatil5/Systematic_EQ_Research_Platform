"""Command-line entry points for reproducible research tasks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from quant_trading.data.loader import MarketDataLoader
from quant_trading.data.universe import get_universe
from quant_trading.features.pipeline import build_feature_dataset
from quant_trading.research.report import write_phase3_report
from quant_trading.research.runner import run_signal_research, save_research_results
from quant_trading.alpha_research.report import write_alpha_report
from quant_trading.alpha_research.runner import run_alpha_research, save_alpha_results
from quant_trading.utils.config import load_research_config
from quant_trading.backtest.runner import run_phase4, save_phase4_results
from quant_trading.backtest.report import write_phase4_report
from quant_trading.prospective.operations import (
    audit_command, signal_command, unavailable_data_command, verify_command,
)
from quant_trading.prospective.report import write_operational_report
from quant_trading.prospective.bloomberg import import_bloomberg


def download_data(config_path: str, universe_name: str) -> None:
    config = load_research_config(config_path)
    loader = MarketDataLoader(config.data.cache_dir)
    result = loader.load(
        get_universe(universe_name),
        start=config.data.start,
        end=config.data.end,
        refresh=config.data.refresh,
        max_abs_daily_return=config.validation.max_abs_daily_return,
        allow_zero_volume=config.validation.allow_zero_volume,
    )
    output = Path(config.data.processed_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.panel.to_parquet(output)
    summary = {
        ticker: {
            "rows": report.output_rows,
            "duplicates_removed": report.duplicate_rows_removed,
            "extreme_return_rows": report.extreme_return_rows,
        }
        for ticker, report in result.quality_reports.items()
    }
    print(f"Saved {len(result.panel):,} rows to {output}")
    print(json.dumps(summary, indent=2))


def build_features(config_path: str) -> None:
    """Build and save Phase 2 features without modifying the canonical panel."""
    config = load_research_config(config_path)
    source = Path(config.data.processed_path)
    if not source.exists():
        raise FileNotFoundError(
            f"Canonical panel not found at {source}; run quant-research download-data first"
        )
    panel = pd.read_parquet(source)
    result = build_feature_dataset(panel, config.features)
    output = Path(config.features.output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.data.to_parquet(output)
    print(f"Saved {len(result.data):,} rows to {output}")
    print(json.dumps(result.summary.to_dict(), indent=2))


def analyze_signals(config_path: str) -> None:
    """Run Phase 3 diagnostics from the saved Phase 2 dataset."""
    config = load_research_config(config_path)
    feature_path = Path(config.features.output_path)
    if not feature_path.exists():
        raise FileNotFoundError(
            f"Feature dataset not found at {feature_path}; run quant-research build-features first"
        )
    dataset = pd.read_parquet(feature_path)
    panel_path = Path(config.data.processed_path)
    panel = pd.read_parquet(panel_path) if panel_path.exists() else None
    results = run_signal_research(
        dataset, config.features, config.signal_research, canonical_panel=panel
    )
    output = Path(config.signal_research.output_dir)
    save_research_results(results, output)
    from quant_trading.research.plots import create_research_plots
    create_research_plots(
        output / "figures", results.scorecard, results.daily_ic, results.yearly_ic,
        results.quantile_returns, results.signal_decay, results.correlations,
        results.turnover, results.regime_results,
    )
    write_phase3_report(
        output / "phase3_signal_research.md", results.scorecard,
        results.correlated_pairs, results.calendar_audit, dataset_rows=len(dataset),
        bootstrap_enabled=config.signal_research.bootstrap.enabled,
    )
    counts = results.scorecard["classification"].value_counts().to_dict()
    print(f"Analyzed {len(results.scorecard)} signals; outputs saved to {output}")
    print(json.dumps(counts, indent=2))


def expand_alpha_research(config_path: str) -> None:
    """Run the frozen post-Phase-3 development/confirmation research design."""
    config = load_research_config(config_path)
    panel_path = Path(config.data.processed_path)
    feature_path = Path(config.features.output_path)
    missing = [str(path) for path in (panel_path, feature_path) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Required real-data artifacts are missing: {missing}")
    panel = pd.read_parquet(panel_path)
    features = pd.read_parquet(feature_path)
    results = run_alpha_research(panel, features, config.alpha_research)
    output = Path(config.alpha_research.output_dir)
    save_alpha_results(results, output)
    write_alpha_report(results, output / "phase3_5_alpha_research.md")
    from quant_trading.alpha_research.report import create_alpha_figures
    create_alpha_figures(results, output / "figures")
    registry_path = output / "hypothesis_registry.csv"
    registry = pd.read_csv(registry_path)
    registry["status"] = "EVALUATED"
    registry.to_csv(registry_path, index=False)
    print(f"Phase 3.5 complete; outputs saved to {output}")


def run_realistic_backtest(config_path: str) -> None:
    """Run only the frozen Phase 4 portfolio and robustness design."""
    config = load_research_config(config_path)
    panel = pd.read_parquet(config.data.processed_path)
    features = pd.read_parquet(config.features.output_path)
    results = run_phase4(panel, features, config.backtest, config.alpha_research)
    output = Path(config.backtest.output_dir)
    save_phase4_results(results, output)
    from quant_trading.backtest.plots import create_phase4_figures
    create_phase4_figures(results, output / "figures")
    decision = write_phase4_report(results, output / "phase4_realistic_backtest.md")
    print(f"Phase 4 complete; Decision {decision}; outputs saved to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Quantitative research platform")
    subparsers = parser.add_subparsers(dest="command", required=True)
    download = subparsers.add_parser("download-data", help="Build the adjusted daily panel")
    download.add_argument("--config", default="config/research.yaml")
    download.add_argument("--universe", default="development")
    features = subparsers.add_parser("build-features", help="Build Phase 2 features and targets")
    features.add_argument("--config", default="config/research.yaml")
    research = subparsers.add_parser("analyze-signals", help="Run Phase 3 signal research")
    research.add_argument("--config", default="config/research.yaml")
    alpha = subparsers.add_parser(
        "expand-alpha-research", help="Run frozen Phase 3.5 alpha research"
    )
    alpha.add_argument("--config", default="config/research.yaml")
    backtest = subparsers.add_parser(
        "run-realistic-backtest", help="Run frozen Phase 4 realistic backtests"
    )
    backtest.add_argument("--config", default="config/research.yaml")
    bloomberg = subparsers.add_parser("bloomberg-import", help="Import Bloomberg XLSX security master")
    bloomberg.add_argument("--snapshot-date", required=True)
    bloomberg.add_argument("--input-dir", required=True)
    bloomberg.add_argument("--config", default="config/prospective.yaml")
    for name, help_text in (
        ("prospective-signal", "Create an immutable after-close Stage A event"),
        ("prospective-execute", "Capture a frozen shadow execution event"),
        ("prospective-mark", "Mark prospective shadow accounts at end of day"),
        ("prospective-report", "Write the latest prospective operational report"),
        ("prospective-verify", "Verify prospective artifact hashes"),
        ("prospective-audit", "Audit prospective experiment integrity"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--config", default="config/prospective.yaml")
    args = parser.parse_args()
    if args.command == "download-data":
        download_data(args.config, args.universe)
    elif args.command == "build-features":
        build_features(args.config)
    elif args.command == "analyze-signals":
        analyze_signals(args.config)
    elif args.command == "expand-alpha-research":
        expand_alpha_research(args.config)
    elif args.command == "run-realistic-backtest":
        run_realistic_backtest(args.config)
    elif args.command == "bloomberg-import":
        result = import_bloomberg(args.snapshot_date, args.input_dir, args.config)
        print(json.dumps(result.summary, indent=2, default=str))
    elif args.command == "prospective-signal":
        signal_command(args.config)
    elif args.command in ("prospective-execute", "prospective-mark"):
        unavailable_data_command(args.command, args.config)
    elif args.command == "prospective-report":
        print(json.dumps(write_operational_report(args.config), indent=2))
    elif args.command == "prospective-verify":
        result = verify_command(args.config)
        print(result.to_string(index=False) if not result.empty else "No manifested artifacts yet")
    elif args.command == "prospective-audit":
        print(json.dumps(audit_command(args.config), indent=2))


if __name__ == "__main__":
    main()
