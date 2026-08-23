"""Reproducible orchestration of Phase 3 statistical research."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from quant_trading.features.metadata import base_metadata
from quant_trading.research.bootstrap import block_bootstrap_mean_ci
from quant_trading.research.calendar_audit import audit_panel_calendar
from quant_trading.research.correlation import highly_correlated_pairs, signal_correlation_matrix
from quant_trading.research.ic import daily_information_coefficients, infer_ic, non_overlapping_inference
from quant_trading.research.multiple_testing import adjust_pvalues
from quant_trading.research.quantiles import quantile_return_series, summarize_quantiles
from quant_trading.research.regimes import build_market_regimes, summarize_ic_by_regime
from quant_trading.research.stability import period_ic_summary, signal_decay
from quant_trading.research.turnover import signal_turnover
from quant_trading.utils.config import FeatureConfig, SignalResearchConfig


@dataclass(frozen=True)
class ResearchResults:
    scorecard: pd.DataFrame
    daily_ic: pd.DataFrame
    non_overlapping_ic: pd.DataFrame
    yearly_ic: pd.DataFrame
    quarterly_ic: pd.DataFrame
    quantile_returns: pd.DataFrame
    signal_decay: pd.DataFrame
    turnover: pd.DataFrame
    correlations: pd.DataFrame
    correlated_pairs: pd.DataFrame
    regime_results: pd.DataFrame
    calendar_audit: dict[str, object] | None


def _high_liquidity_subset(
    dataset: pd.DataFrame, liquidity_feature: str, fraction: float
) -> pd.DataFrame:
    if liquidity_feature not in dataset:
        raise ValueError(f"Liquidity feature {liquidity_feature!r} is missing")
    percentile = dataset[liquidity_feature].groupby(level="date").rank(pct=True)
    return dataset.loc[percentile >= 1.0 - fraction]


def _classification(row: pd.Series, config: SignalResearchConfig) -> str:
    thresholds = config.classification
    direction = int(row["expected_direction"])
    aligned_ic = row["mean_rank_ic"] * direction if direction else abs(row["mean_rank_ic"])
    if not np.isfinite(aligned_ic) or aligned_ic <= 0:
        return "REJECT"
    if direction == 0:
        return "WEAK / INCONCLUSIVE"
    common = (
        aligned_ic >= thresholds.minimum_abs_ic
        and row["fdr_q_value"] <= thresholds.promising_fdr
        and row["expected_positive_year_pct"] >= thresholds.minimum_positive_year_fraction
        and row["turnover"] <= thresholds.maximum_daily_turnover
        and row["liquidity_robustness"] > 0
        and row["expected_monotonicity"] >= 0.50
    )
    if not common:
        return "WEAK / INCONCLUSIVE"
    strong = (
        row["fdr_q_value"] <= thresholds.strong_fdr
        and abs(row["hac_t_stat"]) >= 3.0
        and row["expected_monotonicity"] >= 0.75
        and row["multiple_testing_flag"] == "FDR significant"
    )
    return "STRONG RESEARCH CANDIDATE" if strong else "PROMISING"


def run_signal_research(
    dataset: pd.DataFrame,
    feature_config: FeatureConfig,
    config: SignalResearchConfig,
    *,
    canonical_panel: pd.DataFrame | None = None,
) -> ResearchResults:
    if not isinstance(dataset.index, pd.MultiIndex) or dataset.index.names != ["date", "ticker"]:
        raise ValueError("Research dataset must have a (date, ticker) MultiIndex")
    candidates = tuple(candidate.name for candidate in config.candidates)
    required = set(candidates) | {config.primary_target, config.liquidity_feature}
    required |= {f"target_return_{horizon}d" for horizon in config.horizons}
    missing = required - set(dataset.columns)
    if missing:
        raise ValueError(f"Research dataset is missing required columns: {sorted(missing)}")
    if any(signal.startswith("target_") for signal in candidates):
        raise ValueError("Target columns cannot enter candidate signal analysis")

    metadata = base_metadata(
        feature_config.return_lookbacks,
        feature_config.moving_average_windows,
        feature_config.volatility_windows,
    )
    high_liquidity = _high_liquidity_subset(
        dataset, config.liquidity_feature, config.high_liquidity_fraction
    )
    regimes = build_market_regimes(dataset, benchmark=feature_config.market_benchmark)
    score_rows: list[dict[str, object]] = []
    daily_frames = []
    nonoverlap_frames = []
    yearly_frames = []
    quarterly_frames = []
    quantile_frames = []
    turnover_frames = []
    regime_frames = []

    for candidate in config.candidates:
        signal = candidate.name
        daily = daily_information_coefficients(
            dataset, signal, config.primary_target,
            minimum_cross_section=config.minimum_cross_section,
        )
        inference = infer_ic(daily["spearman_ic"], hac_lags=config.hac_lags)
        daily_frames.append(daily.assign(signal=signal).reset_index())
        nonoverlap_frames.append(
            non_overlapping_inference(daily["spearman_ic"], config.target_horizon)
            .assign(signal=signal).reset_index()
        )
        yearly = period_ic_summary(daily["spearman_ic"], "Y", config.hac_lags)
        quarterly = period_ic_summary(daily["spearman_ic"], "Q", config.hac_lags)
        yearly_frames.append(yearly.assign(signal=signal).reset_index())
        quarterly_frames.append(quarterly.assign(signal=signal).reset_index())

        quantiles = quantile_return_series(
            dataset, signal, config.primary_target, quantiles=config.quantiles,
            minimum_cross_section=config.minimum_cross_section,
        )
        quantile_frames.append(quantiles.assign(signal=signal).reset_index())
        qsummary = summarize_quantiles(quantiles, candidate.expected_direction)
        daily_turnover = signal_turnover(dataset, signal, quantiles=config.quantiles)
        five_day_turnover = signal_turnover(
            dataset, signal, quantiles=config.quantiles, rebalance_step=config.target_horizon
        )
        turnover_frames.append(daily_turnover.assign(signal=signal, frequency="daily").reset_index())
        turnover_frames.append(five_day_turnover.assign(signal=signal, frequency="5_session").reset_index())
        regime = summarize_ic_by_regime(daily["spearman_ic"], regimes)
        regime_frames.append(regime.assign(signal=signal))

        liquid_ic = daily_information_coefficients(
            high_liquidity, signal, config.primary_target,
            minimum_cross_section=config.minimum_cross_section,
        )
        liquid_mean = float(liquid_ic["spearman_ic"].mean()) if not liquid_ic.empty else np.nan
        year_means = yearly["mean"] if not yearly.empty else pd.Series(dtype=float)
        expected_years = (
            year_means * candidate.expected_direction
            if candidate.expected_direction else pd.Series(dtype=float)
        )
        bootstrap_ic = (np.nan, np.nan)
        bootstrap_spread = (np.nan, np.nan)
        if config.bootstrap.enabled:
            bootstrap_ic = block_bootstrap_mean_ci(
                daily["spearman_ic"], iterations=config.bootstrap.iterations,
                block_length=config.bootstrap.block_length, seed=config.bootstrap.seed,
            )
            bootstrap_spread = block_bootstrap_mean_ci(
                quantiles.get("q_high_minus_low", pd.Series(dtype=float)),
                iterations=config.bootstrap.iterations, block_length=config.bootstrap.block_length,
                seed=config.bootstrap.seed,
            )
        direction = candidate.expected_direction or 1
        score_rows.append({
            "signal": signal,
            "category": metadata[signal].category if signal in metadata else "configured",
            "expected_direction": candidate.expected_direction,
            "valid_dates": inference.valid_dates,
            "mean_rank_ic": inference.mean,
            "median_rank_ic": inference.median,
            "ic_ir": inference.information_ratio,
            "naive_t_stat": inference.naive_t_stat,
            "hac_t_stat": inference.hac_t_stat,
            "raw_p_value": inference.hac_p_value,
            "positive_ic_pct": inference.positive_percentage,
            "q1_return": qsummary.returns.get(1, np.nan),
            "q5_return": qsummary.returns.get(config.quantiles, np.nan),
            "q5_minus_q1": qsummary.q5_minus_q1,
            "quantile_monotonicity": qsummary.quantile_rank_correlation,
            "expected_monotonicity": qsummary.adjacent_fraction_expected,
            "rank_autocorrelation": float(daily_turnover.get("rank_autocorrelation", pd.Series(dtype=float)).mean()),
            "turnover": float(daily_turnover.get("top_turnover", pd.Series(dtype=float)).mean()),
            "turnover_5d": float(five_day_turnover.get("top_turnover", pd.Series(dtype=float)).mean()),
            "positive_year_pct": float((year_means > 0).mean()) if len(year_means) else np.nan,
            "expected_positive_year_pct": (
                float((expected_years > 0).mean()) if len(expected_years) else np.nan
            ),
            "worst_year_ic": float(year_means.min()) if len(year_means) else np.nan,
            "best_year_ic": float(year_means.max()) if len(year_means) else np.nan,
            "liquidity_robustness": liquid_mean * direction,
            "bootstrap_ic_low": bootstrap_ic[0], "bootstrap_ic_high": bootstrap_ic[1],
            "bootstrap_spread_low": bootstrap_spread[0], "bootstrap_spread_high": bootstrap_spread[1],
        })

    scorecard = pd.DataFrame(score_rows)
    adjustments = adjust_pvalues(scorecard.set_index("signal")["raw_p_value"])
    scorecard = scorecard.drop(columns="raw_p_value").merge(
        adjustments.reset_index().rename(columns={"index": "signal"}), on="signal", how="left"
    )
    scorecard["multiple_testing_flag"] = np.where(
        scorecard["fdr_q_value"] <= config.fdr_alpha, "FDR significant",
        np.where(scorecard["bonferroni_p_value"] <= config.bonferroni_alpha, "Bonferroni only", "Not adjusted-significant"),
    )
    expected_aligned = scorecard["mean_rank_ic"] * scorecard["expected_direction"].replace(0, np.nan)
    scorecard["stability_flag"] = np.where(
        scorecard["expected_positive_year_pct"] >= config.classification.minimum_positive_year_fraction,
        "stable sign", "unstable sign"
    )
    scorecard.loc[scorecard["expected_direction"] == 0, "stability_flag"] = "direction unknown"
    scorecard.loc[expected_aligned <= 0, "stability_flag"] = "wrong overall sign"
    scorecard["classification"] = scorecard.apply(_classification, axis=1, config=config)

    correlations = signal_correlation_matrix(
        dataset, candidates, minimum_cross_section=config.minimum_cross_section
    )
    pairs = highly_correlated_pairs(correlations, config.correlation_flag_threshold)
    calendar = audit_panel_calendar(canonical_panel).to_dict() if canonical_panel is not None else None
    concat = lambda frames: pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return ResearchResults(
        scorecard, concat(daily_frames), concat(nonoverlap_frames), concat(yearly_frames),
        concat(quarterly_frames), concat(quantile_frames),
        signal_decay(dataset, candidates, config.horizons, config.minimum_cross_section),
        concat(turnover_frames), correlations, pairs, concat(regime_frames), calendar,
    )


def save_research_results(results: ResearchResults, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    results.scorecard.to_csv(output_dir / "signal_scorecard.csv", index=False)
    results.daily_ic.to_parquet(output_dir / "daily_ic.parquet", index=False)
    results.non_overlapping_ic.to_csv(output_dir / "non_overlapping_ic.csv", index=False)
    results.yearly_ic.to_csv(output_dir / "yearly_ic.csv", index=False)
    results.quarterly_ic.to_csv(output_dir / "quarterly_ic.csv", index=False)
    results.quantile_returns.to_csv(output_dir / "quantile_returns.csv", index=False)
    results.signal_decay.to_csv(output_dir / "signal_decay.csv", index=False)
    results.turnover.to_csv(output_dir / "turnover.csv", index=False)
    results.correlations.to_csv(output_dir / "signal_correlations.csv")
    results.correlated_pairs.to_csv(output_dir / "high_correlation_pairs.csv", index=False)
    results.regime_results.to_csv(output_dir / "regime_results.csv", index=False)
    if results.calendar_audit is not None:
        pd.Series(results.calendar_audit).to_json(output_dir / "calendar_audit.json", indent=2)
