"""Compact diagnostic figure set for Phase 4."""

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd


def create_phase4_figures(results, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    core, benchmarks = results["core_results"], results["benchmarks"]
    fig, ax = plt.subplots(figsize=(10, 5))
    for name, result in core.items():
        curve = result.daily.equity / result.daily.equity.iloc[0]
        ax.plot(curve.index, curve, label=name)
    ax.plot(benchmarks.index, (1 + benchmarks.spy).cumprod(), label="SPY", alpha=.7)
    ax.set_yscale("log"); ax.set_title("Growth of one dollar"); ax.legend(); fig.tight_layout()
    fig.savefig(output / "equity_curves.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    primary = core["primary"].daily
    ax.plot(primary.index, primary.equity / primary.equity.iloc[0], label="primary")
    ax.plot(benchmarks.index, (1 + benchmarks.equal_weight).cumprod(), label="equal-weight universe")
    ax.set_yscale("log"); ax.set_title("Primary vs equal-weight universe"); ax.legend(); fig.tight_layout()
    fig.savefig(output / "equity_vs_equal_weight.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4))
    for name in ("primary", "challenger"):
        equity = core[name].daily.equity
        ax.plot(equity.index, equity / equity.cummax() - 1, label=name)
    ax.set_title("Drawdowns"); ax.legend(); fig.tight_layout()
    fig.savefig(output / "drawdowns.png", dpi=150); plt.close(fig)

    returns = core["primary"].daily.net_return
    rolling_return = (1 + returns).rolling(252).apply(lambda x: x.prod(), raw=True) - 1
    rolling_sharpe = returns.rolling(252).mean() / returns.rolling(252).std() * (252 ** .5)
    for series, title, filename in (
        (rolling_return, "Rolling 12-month return", "rolling_12m_return.png"),
        (rolling_sharpe, "Rolling 12-month zero-rate Sharpe", "rolling_sharpe.png"),
        (results.get("primary_rolling_beta", pd.Series(dtype=float)), "Rolling beta to SPY", "rolling_beta.png"),
    ):
        fig, ax = plt.subplots(figsize=(10, 4)); ax.plot(series.index, series)
        ax.set_title(title); fig.tight_layout(); fig.savefig(output / filename, dpi=150); plt.close(fig)

    monthly = (1 + returns).groupby([returns.index.year, returns.index.month]).prod() - 1
    heat = monthly.unstack().sort_index()
    fig, ax = plt.subplots(figsize=(11, 6)); image = ax.imshow(heat, aspect="auto", cmap="RdYlGn")
    ax.set_yticks(range(len(heat))); ax.set_yticklabels(heat.index); ax.set_xticks(range(12)); ax.set_xticklabels(range(1, 13))
    ax.set_title("Primary monthly returns"); fig.colorbar(image, ax=ax); fig.tight_layout()
    fig.savefig(output / "monthly_return_heatmap.png", dpi=150); plt.close(fig)

    annual = results["yearly_summary"].pivot(index="year", columns="strategy", values="strategy_return")
    fig, ax = plt.subplots(figsize=(11, 5)); annual.plot.bar(ax=ax); ax.set_title("Annual returns"); fig.tight_layout()
    fig.savefig(output / "annual_returns.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4)); ax.plot(primary.index, primary.turnover, alpha=.7)
    ax.set_title("Primary daily turnover"); fig.tight_layout(); fig.savefig(output / "turnover.png", dpi=150); plt.close(fig)

    exposures = results.get("primary_sector_exposures", pd.DataFrame())
    if not exposures.empty:
        pivot = exposures.pivot_table(index="date", columns="sector", values="weight", aggfunc="sum", fill_value=0)
        fig, ax = plt.subplots(figsize=(11, 6)); pivot.plot.area(ax=ax); ax.set_title("Primary sector exposure")
        ax.legend(loc="center left", bbox_to_anchor=(1, .5)); fig.tight_layout(); fig.savefig(output / "sector_exposure.png", dpi=150); plt.close(fig)

    for test in ("cost", "delay", "top_n", "frequency"):
        subset = results["sensitivity"].query("test == @test")
        fig, ax = plt.subplots(figsize=(8, 4))
        for strategy, group in subset.groupby("strategy"):
            ax.plot(group.value.astype(str), group.cagr, marker="o", label=strategy)
        ax.set_title(f"Confirmation CAGR: {test}"); ax.legend(); fig.tight_layout()
        fig.savefig(output / f"sensitivity_{test}.png", dpi=150); plt.close(fig)

    primary_cagr = results["strategy_summary"].query("strategy == 'primary' and sample == 'CONFIRMATION'").cagr.iloc[0]
    for kind, filename, title in (("random_selection", "random_baseline.png", "Random baseline"),
                                  ("scrambled_signal", "signal_scramble.png", "Signal scramble")):
        group = results["randomization"].query("kind == @kind")
        fig, ax = plt.subplots(figsize=(8, 4)); ax.hist(group.cagr, bins=20, alpha=.7)
        ax.axvline(primary_cagr, color="black", label="primary"); ax.set_title(f"{title}: confirmation CAGR")
        ax.legend(); fig.tight_layout(); fig.savefig(output / filename, dpi=150); plt.close(fig)
