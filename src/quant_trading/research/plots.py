"""Non-interactive Phase 3 research visualizations."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def create_research_plots(
    figures: Path,
    scorecard: pd.DataFrame,
    daily_ic: pd.DataFrame,
    yearly_ic: pd.DataFrame,
    quantile_returns: pd.DataFrame,
    decay: pd.DataFrame,
    correlations: pd.DataFrame,
    turnover: pd.DataFrame,
    regime_results: pd.DataFrame,
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures.mkdir(parents=True, exist_ok=True)

    def save(name: str) -> None:
        plt.tight_layout()
        plt.savefig(figures / name, dpi=150, bbox_inches="tight")
        plt.close()

    scorecard.sort_values("mean_rank_ic").plot.barh(x="signal", y="mean_rank_ic", legend=False, figsize=(8, 7), title="Mean daily rank IC")
    save("mean_rank_ic.png")
    scorecard.plot.scatter(x="turnover", y="mean_rank_ic", figsize=(7, 5), title="IC vs membership turnover")
    save("ic_vs_turnover.png")
    scorecard.plot.scatter(x="mean_rank_ic", y="hac_t_stat", figsize=(7, 5), title="HAC t-stat vs mean rank IC")
    save("hac_tstat_vs_ic.png")
    scorecard.sort_values("turnover").plot.barh(x="signal", y="turnover", legend=False, figsize=(8, 7), title="Daily top-quantile turnover")
    save("turnover.png")

    selected = scorecard.sort_values("fdr_q_value", na_position="last")["signal"].iloc[0] if len(scorecard) else None
    if selected is not None:
        ic = daily_ic[daily_ic["signal"] == selected].set_index("date")["spearman_ic"]
        ic.plot(figsize=(10, 4), title=f"Daily rank IC: {selected}")
        save("selected_signal_ic.png")
        ic.rolling(126, min_periods=60).mean().plot(figsize=(10, 4), title=f"Rolling 6-month rank IC: {selected}")
        save("selected_signal_rolling_ic.png")
        years = yearly_ic[yearly_ic["signal"] == selected]
        if not years.empty:
            years.plot.bar(x="period", y="mean", legend=False, figsize=(9, 4), title=f"Yearly rank IC: {selected}")
            save("selected_signal_yearly_ic.png")
        quantile = quantile_returns[quantile_returns["signal"] == selected].set_index("date")
        qcols = [column for column in quantile if column.startswith("q") and column[1:].isdigit()]
        if qcols:
            quantile[qcols].mean().plot.bar(figsize=(7, 4), title=f"Average forward returns: {selected}")
            save("selected_signal_quantiles.png")
            (1 + quantile[qcols + ["q_high_minus_low"]].fillna(0)).cumprod().plot(
                figsize=(10, 5), title=f"Forward-return diagnostic curves: {selected}"
            )
            save("selected_signal_quantile_curves.png")
    if not decay.empty:
        decay.pivot(index="horizon", columns="signal", values="mean_rank_ic").plot(figsize=(10, 6), marker="o", title="Signal decay")
        save("signal_decay.png")
    if not correlations.empty:
        plt.figure(figsize=(10, 8))
        plt.imshow(correlations, vmin=-1, vmax=1, cmap="coolwarm")
        plt.xticks(range(len(correlations)), correlations.columns, rotation=90, fontsize=7)
        plt.yticks(range(len(correlations)), correlations.index, fontsize=7)
        plt.colorbar(label="Mean daily Spearman correlation")
        plt.title("Signal correlation")
        save("signal_correlations.png")
    if not regime_results.empty:
        regime_results.groupby(["regime_type", "regime"])["mean_rank_ic"].mean().plot.bar(figsize=(8, 4), title="Mean IC by regime")
        save("regime_comparison.png")

