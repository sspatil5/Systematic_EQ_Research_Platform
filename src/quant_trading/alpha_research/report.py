"""Phase 3.5 report and compact non-interactive figures."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _text_table(frame: pd.DataFrame, columns: list[str]) -> str:
    selected = frame[[column for column in columns if column in frame]]
    return f"```text\n{selected.to_string(index=False)}\n```"


def write_alpha_report(results: dict[str, pd.DataFrame], output: Path) -> None:
    development = results["development_results"]
    confirmation = results["confirmation_results"]
    fm = results["fama_macbeth_results"]
    reversal = results["reversal_cost_analysis"]
    long_only = results["long_only_analysis"]
    text = f"""# Phase 3.5 — Alpha research expansion

All tests in this report are **POST-PHASE-3 HYPOTHESES**. Development is 2010–2021 and the
untuned confirmation period is 2022–2026. Current sector labels are research controls, not
point-in-time historical classifications. Nothing here is executable strategy P&L.

## Development signal results

{_text_table(development, ['signal','family','mean_rank_ic','hac_t_stat','p_value','family_fdr_q_value','q_high_minus_low','monotonicity'])}

## Confirmation signal results

{_text_table(confirmation, ['signal','family','mean_rank_ic','hac_t_stat','p_value','family_fdr_q_value','q_high_minus_low','monotonicity'])}

## Fama–MacBeth exposure controls

Predictors are standardized within each date. Coefficients are cross-sectional associations, not
causal estimates. HAC inference is applied to the daily coefficient time series.

{_text_table(fm, ['sample','model','predictor','mean_coefficient','hac_t_stat','p_value','family_fdr_q_value','positive_coefficient_pct','sector_controls'])}

## Reversal cost diagnostics

Break-even cost is the diagnostic low-minus-high spread divided by two-leg membership turnover.
It omits open execution, spread asymmetry, market impact, and portfolio constraints.

{_text_table(reversal, ['sample','regime','tail_fraction','oriented_low_minus_high_spread','two_leg_turnover','break_even_one_way_bps','mean_rank_ic','hac_t_stat'])}

## Long-only relevance

{_text_table(long_only, ['sample','signal','selected_absolute_return','selected_minus_universe','selected_minus_spy','opposite_minus_universe'])}

## Integrity limitations

- Phase 3.5 hypotheses were chosen after inspecting Phase 3, so development significance is not
  pre-registration-quality evidence.
- Confirmation definitions were frozen before this run and were not tuned after observation.
- Present-day universe and sector labels introduce survivorship and classification bias.
- Five-day targets are close-to-close labels and not next-open executable returns.
- Sector groups are small for Energy, Materials, Utilities, and ETFs; minimum group rules create
  missing sector-neutral observations rather than silently pooling them.
"""
    output.write_text(text, encoding="utf-8")


def create_alpha_figures(results: dict[str, pd.DataFrame], figures: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures.mkdir(parents=True, exist_ok=True)
    comparison = pd.concat([
        results["development_results"].assign(period="development"),
        results["confirmation_results"].assign(period="confirmation"),
    ])
    pivot = comparison.pivot(index="signal", columns="period", values="mean_rank_ic")
    pivot.plot.barh(figsize=(9, 9), title="Development vs confirmation rank IC")
    plt.tight_layout(); plt.savefig(figures / "development_confirmation_ic.png", dpi=150); plt.close()
    momentum = comparison[comparison.family == "momentum_variants"]
    momentum.pivot(index="signal", columns="period", values="mean_rank_ic").plot.bar(
        figsize=(9, 5), title="Predefined momentum variants"
    )
    plt.tight_layout(); plt.savefig(figures / "momentum_variants.png", dpi=150); plt.close()
    fm = results["fama_macbeth_results"]
    vol = fm[fm.predictor == "realized_vol_20"]
    vol.pivot(index="model", columns="sample", values="mean_coefficient").plot.bar(
        figsize=(9, 5), title="Volatility coefficient after controls"
    )
    plt.tight_layout(); plt.savefig(figures / "volatility_controls.png", dpi=150); plt.close()
    combo = comparison[comparison.family == "combinations"]
    combo.pivot(index="signal", columns="period", values="mean_rank_ic").plot.bar(
        figsize=(9, 5), title="Transparent signal combinations"
    )
    plt.tight_layout(); plt.savefig(figures / "signal_combinations.png", dpi=150); plt.close()
