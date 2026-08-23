"""Phase 3.5 post-selection alpha-research orchestration."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from quant_trading.alpha_research.diagnostics import (
    long_only_diagnostics, orthogonality_table, signal_summary, tail_reversal_diagnostics,
)
from quant_trading.alpha_research.fama_macbeth import (
    RegressionSpecification, daily_cross_sectional_regression, summarize_coefficients,
)
from quant_trading.alpha_research.features import (
    build_momentum_expansion, decompose_daily_returns, idiosyncratic_volatility_60,
)
from quant_trading.alpha_research.sectors import SECTOR_MAP, sector_series
from quant_trading.alpha_research.split import split_development_confirmation
from quant_trading.alpha_research.transforms import (
    cross_sectional_zscore, equal_weight_combination, residualize_cross_sectionally,
    sector_neutral_zscore,
)
from quant_trading.research.multiple_testing import adjust_pvalues
from quant_trading.research.regimes import build_market_regimes
from quant_trading.utils.config import AlphaResearchConfig


SIGNAL_FAMILIES = {
    "momentum_6_1": "momentum_variants", "momentum_9_1": "momentum_variants",
    "momentum_12_1": "momentum_variants", "momentum_12_2": "momentum_variants",
    "risk_adjusted_momentum_12_1": "momentum_variants",
    "positive_week_fraction_52": "trend_consistency",
    "positive_month_fraction_12": "trend_consistency",
    "sector_neutral_momentum_12_1": "momentum_controls",
    "residual_momentum_beta": "momentum_controls",
    "residual_momentum_beta_sector": "momentum_controls",
    "sector_neutral_realized_vol_20": "volatility_controls",
    "residual_volatility_beta": "volatility_controls",
    "residual_volatility_beta_sector": "volatility_controls",
    "idiosyncratic_volatility_60": "volatility_controls",
    "combined_momentum_volatility": "combinations",
    "combined_momentum_reversal": "combinations",
    "combined_momentum_volatility_reversal": "combinations",
    "conditional_momentum_reversal": "combinations",
    "overnight_reversal": "reversal", "intraday_reversal": "reversal",
}


def build_alpha_dataset(
    panel: pd.DataFrame, features: pd.DataFrame, config: AlphaResearchConfig
) -> tuple[pd.DataFrame, pd.Series]:
    if not panel.index.equals(features.index):
        raise ValueError("Canonical panel and feature dataset indexes must match")
    output = features.copy()
    sectors = sector_series(output.index)
    expansion = build_momentum_expansion(panel, output)
    for column in expansion:
        output[column] = expansion[column]
    decomposition = decompose_daily_returns(panel)
    for column in decomposition:
        output[column] = decomposition[column]
    output["idiosyncratic_volatility_60"] = idiosyncratic_volatility_60(output)

    for signal in ("momentum_12_1", "realized_vol_20", "downside_vol_20", "ret_1d", "ret_5d"):
        output[f"sector_neutral_{signal}"] = sector_neutral_zscore(
            output[signal], sectors, minimum_group=config.minimum_sector_size
        )
    output["residual_momentum_beta"] = residualize_cross_sectionally(
        output["momentum_12_1"], output[["beta_20"]],
        minimum_observations=config.minimum_cross_section,
    )
    output["residual_momentum_beta_sector"] = residualize_cross_sectionally(
        output["momentum_12_1"], output[["beta_20"]], sectors=sectors,
        minimum_observations=config.minimum_cross_section,
    )
    output["residual_volatility_beta"] = residualize_cross_sectionally(
        output["realized_vol_20"], output[["beta_20"]],
        minimum_observations=config.minimum_cross_section,
    )
    output["residual_volatility_beta_sector"] = residualize_cross_sectionally(
        output["realized_vol_20"], output[["beta_20"]], sectors=sectors,
        minimum_observations=config.minimum_cross_section,
    )
    reversal = -output["ret_1d"]
    output["combined_momentum_volatility"] = equal_weight_combination(
        output[["momentum_12_1", "residual_volatility_beta"]]
    )
    output["combined_momentum_reversal"] = equal_weight_combination(
        pd.DataFrame({"momentum": output["momentum_12_1"], "reversal": reversal})
    )
    output["combined_momentum_volatility_reversal"] = equal_weight_combination(
        pd.DataFrame({
            "momentum": output["momentum_12_1"],
            "volatility": output["residual_volatility_beta"], "reversal": reversal,
        })
    )
    regimes = build_market_regimes(output)
    high = pd.Series(
        output.index.get_level_values("date").map(regimes["volatility_regime"].eq("high")),
        index=output.index,
    ).astype(float)
    output["conditional_momentum_reversal"] = (
        cross_sectional_zscore(output["momentum_12_1"])
        + 0.25 * high * cross_sectional_zscore(reversal)
    )
    return output, sectors


def _evaluate_signals(
    dataset: pd.DataFrame, signals: tuple[str, ...], config: AlphaResearchConfig, sample: str
) -> pd.DataFrame:
    rows = []
    for signal in signals:
        row = signal_summary(
            dataset, signal, target=config.target, expected_direction=1,
            minimum_cross_section=config.minimum_cross_section, hac_lags=config.hac_lags,
        )
        row.update({"sample": sample, "family": SIGNAL_FAMILIES[signal]})
        rows.append(row)
    result = pd.DataFrame(rows)
    adjusted = []
    for _, family in result.groupby("family"):
        correction = adjust_pvalues(family.set_index("signal")["p_value"])
        adjusted.append(correction["fdr_q_value"])
    qvalues = pd.concat(adjusted)
    result["family_fdr_q_value"] = result["signal"].map(qvalues)
    return result


def run_alpha_research(
    panel: pd.DataFrame,
    features: pd.DataFrame,
    config: AlphaResearchConfig,
) -> dict[str, pd.DataFrame]:
    dataset, sectors = build_alpha_dataset(panel, features, config)
    development, confirmation = split_development_confirmation(
        dataset, development_end=config.development_end,
        confirmation_start=config.confirmation_start,
    )
    development_sectors = sectors.loc[development.index]
    confirmation_sectors = sectors.loc[confirmation.index]
    signals = tuple(SIGNAL_FAMILIES)
    development_results = _evaluate_signals(development, signals, config, "development")
    confirmation_results = _evaluate_signals(confirmation, signals, config, "confirmation")

    specifications = (
        RegressionSpecification("A_momentum", ("momentum_12_1",)),
        RegressionSpecification("B_momentum_beta", ("momentum_12_1", "beta_20")),
        RegressionSpecification("C_momentum_beta_vol", ("momentum_12_1", "beta_20", "realized_vol_20")),
        RegressionSpecification("D_momentum_beta_vol_sector", ("momentum_12_1", "beta_20", "realized_vol_20"), True),
        RegressionSpecification("E_volatility", ("realized_vol_20",)),
        RegressionSpecification("F_volatility_beta", ("realized_vol_20", "beta_20")),
        RegressionSpecification("G_volatility_beta_momentum", ("realized_vol_20", "beta_20", "momentum_12_1")),
        RegressionSpecification("H_volatility_beta_momentum_sector", ("realized_vol_20", "beta_20", "momentum_12_1"), True),
    )
    fm_rows = []
    coefficient_frames = []
    for sample_name, sample, sample_sectors in (
        ("development", development, development_sectors),
        ("confirmation", confirmation, confirmation_sectors),
    ):
        for specification in specifications:
            coefficients = daily_cross_sectional_regression(
                sample, config.target, specification, sectors=sample_sectors,
                minimum_observations=config.minimum_cross_section,
            )
            coefficient_frames.append(coefficients.assign(model=specification.name, sample=sample_name).reset_index())
            summary = summarize_coefficients(coefficients, specification, hac_lags=config.hac_lags)
            fm_rows.append(summary.assign(sample=sample_name))

    reversal_rows = []
    for sample_name, sample in (("development", development), ("confirmation", confirmation)):
        reversal_rows.append(tail_reversal_diagnostics(
            sample, fractions=config.reversal_tail_fractions
        ).assign(sample=sample_name))
        regimes = build_market_regimes(sample)
        for regime in ("high", "low"):
            selected_dates = regimes.index[regimes["volatility_regime"] == regime]
            subset = sample.loc[sample.index.get_level_values("date").isin(selected_dates)]
            summary = signal_summary(
                subset.assign(oriented_reversal=-subset["ret_1d"]), "oriented_reversal",
                target=config.target, minimum_cross_section=config.minimum_cross_section,
                hac_lags=config.hac_lags,
            )
            reversal_rows.append(pd.DataFrame([{**summary, "sample": sample_name, "regime": regime}]))

    important = (
        "momentum_12_1", "sector_neutral_momentum_12_1", "realized_vol_20",
        "idiosyncratic_volatility_60", "combined_momentum_volatility",
    )
    deciles = pd.DataFrame([
        {**signal_summary(sample, signal, target=config.target, quantiles=10,
                          minimum_cross_section=config.minimum_cross_section,
                          hac_lags=config.hac_lags), "sample": sample_name}
        for sample_name, sample in (("development", development), ("confirmation", confirmation))
        for signal in important
    ])
    long_only = pd.DataFrame([
        {**long_only_diagnostics(sample, signal, target=config.target), "sample": sample_name}
        for sample_name, sample in (("development", development), ("confirmation", confirmation))
        for signal in important + ("combined_momentum_reversal", "conditional_momentum_reversal")
    ])
    fama_macbeth_results = pd.concat(fm_rows, ignore_index=True)
    fama_macbeth_results["hypothesis_family"] = np.where(
        fama_macbeth_results["model"].str.startswith(("A_", "B_", "C_", "D_")),
        "momentum_controls", "volatility_controls",
    )
    fama_macbeth_results["family_fdr_q_value"] = np.nan
    primary = (
        ((fama_macbeth_results.hypothesis_family == "momentum_controls")
         & (fama_macbeth_results.predictor == "momentum_12_1"))
        | ((fama_macbeth_results.hypothesis_family == "volatility_controls")
           & (fama_macbeth_results.predictor == "realized_vol_20"))
    )
    for (_, _), group in fama_macbeth_results.loc[primary].groupby(["sample", "hypothesis_family"]):
        adjusted = adjust_pvalues(group.set_index("model")["p_value"])
        for model, qvalue in adjusted["fdr_q_value"].items():
            mask = (fama_macbeth_results["sample"] == group["sample"].iloc[0]) & (fama_macbeth_results["model"] == model)
            fama_macbeth_results.loc[mask & primary, "family_fdr_q_value"] = qvalue

    orthogonality = orthogonality_table(dataset, signals)
    mapping = pd.DataFrame(sorted(SECTOR_MAP.items()), columns=["ticker", "sector"])
    combined_results = pd.concat([development_results, confirmation_results], ignore_index=True)
    return {
        "expanded_dataset": dataset,
        "development_results": development_results,
        "confirmation_results": confirmation_results,
        "fama_macbeth_results": fama_macbeth_results,
        "fama_macbeth_daily": pd.concat(coefficient_frames, ignore_index=True),
        "reversal_cost_analysis": pd.concat(reversal_rows, ignore_index=True),
        "decile_analysis": deciles,
        "long_only_analysis": long_only,
        "orthogonality": orthogonality,
        "sector_mapping": mapping,
        "momentum_variants": combined_results[
            combined_results["family"].isin(["momentum_variants", "trend_consistency"])
        ],
        "neutralized_signal_results": combined_results[
            combined_results["family"].isin(["momentum_controls", "volatility_controls"])
        ],
        "volatility_decomposition": fama_macbeth_results.query(
            "predictor == 'realized_vol_20'"
        ),
        "signal_combinations": combined_results[combined_results["family"] == "combinations"],
    }


def save_alpha_results(results: dict[str, pd.DataFrame], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, frame in results.items():
        if name == "expanded_dataset":
            continue
        frame.to_csv(output / f"{name}.csv", index=False)
    results["sector_mapping"].to_csv("data/processed/sector_mapping.csv", index=False)
