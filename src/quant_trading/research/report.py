"""Markdown report generation with deliberately cautious language."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _table(frame: pd.DataFrame, columns: list[str], rows: int = 20) -> str:
    selected = frame.loc[:, [column for column in columns if column in frame]].head(rows)
    return f"```text\n{selected.to_string(index=False)}\n```" if not selected.empty else "No eligible observations."


def write_phase3_report(
    output: Path,
    scorecard: pd.DataFrame,
    correlated_pairs: pd.DataFrame,
    calendar_audit: dict[str, object] | None,
    *,
    dataset_rows: int,
    bootstrap_enabled: bool,
) -> None:
    classifications = scorecard["classification"].value_counts().to_dict()
    strongest = scorecard.sort_values("fdr_q_value", na_position="last")
    weak = scorecard[scorecard["classification"].isin(["REJECT", "WEAK / INCONCLUSIVE"])]
    audit_text = (
        "Calendar audit was unavailable because the canonical panel was not supplied."
        if calendar_audit is None else "\n".join(f"- {key}: {value}" for key, value in calendar_audit.items())
    )
    text = f"""# Phase 3 signal research

## Executive summary

This report tests cross-sectional predictive evidence; it does **not** demonstrate executable
trading profitability. Research quantile returns use future close-to-close labels and omit execution
timing, transaction costs, capacity, and portfolio constraints.

- Dataset rows: {dataset_rows:,}
- Candidate signals: {len(scorecard)}
- Evidence labels: {classifications}
- Block bootstrap enabled: {bootstrap_enabled}

## Dataset and calendar audit

{audit_text}

## Methodology

The primary statistic is daily cross-sectional Spearman IC versus `target_return_5d`. Pearson IC is
also retained. Five-day labels overlap, so Newey-West inference uses the configured lag and is
prioritized over naive inference. All five non-overlapping offsets are reported rather than selected.
Raw p-values are adjusted across the candidate family using Benjamini-Hochberg FDR and Bonferroni.
Quantiles are diagnostic forward-return research portfolios, not executable P&L.

## IC results and multiple testing

{_table(strongest, ['signal', 'category', 'mean_rank_ic', 'hac_t_stat', 'raw_p_value', 'fdr_q_value', 'bonferroni_p_value', 'classification'])}

## Quantile results and turnover

{_table(scorecard, ['signal', 'q1_return', 'q5_return', 'q5_minus_q1', 'quantile_monotonicity', 'rank_autocorrelation', 'turnover'])}

## Temporal stability, regimes, and liquidity

{_table(scorecard, ['signal', 'positive_year_pct', 'worst_year_ic', 'best_year_ic', 'liquidity_robustness', 'stability_flag'])}

## Signal correlation

Highly correlated pairs are flags for redundant economic ideas, not automatically deleted signals.

{_table(correlated_pairs, ['signal_a', 'signal_b', 'correlation'], rows=50)}

## Top research candidates

{_table(scorecard[scorecard['classification'].isin(['PROMISING', 'STRONG RESEARCH CANDIDATE'])], ['signal', 'mean_rank_ic', 'hac_t_stat', 'fdr_q_value', 'q5_minus_q1', 'turnover', 'classification'])}

## Rejected / weak signals

{_table(weak, ['signal', 'mean_rank_ic', 'hac_t_stat', 'fdr_q_value', 'stability_flag', 'classification'])}

## Known limitations

- The present-day development universe has survivorship and selection bias.
- Per-ticker horizons count observed rows, not a master exchange calendar.
- The target is future close-to-close return, not the return from an executable next-open fill.
- yfinance adjustments and adjusted-close dollar volume are research approximations.
- Quantile curves omit costs and overlapping-label accounting and cannot be interpreted as wealth.
- Regime and subgroup results are diagnostics; repeated slicing creates further multiple-testing risk.

## Conclusion

Evidence labels are intentionally conservative and require agreement across effect size, HAC
inference, FDR, monotonicity, temporal stability, turnover, and liquidity conditioning. Phase 3 can
justify continued research, but never live capital or even executable profitability by itself.
"""
    output.write_text(text, encoding="utf-8")
