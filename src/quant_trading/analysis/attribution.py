"""Security contribution and concentration diagnostics."""

import pandas as pd


def contribution_table(result) -> pd.DataFrame:
    contribution = result.contributions.sort_values(ascending=False)
    frame = contribution.rename("pnl_contribution").reset_index().rename(columns={"index": "ticker"})
    total_abs = contribution.abs().sum()
    frame["absolute_contribution_share"] = frame.pnl_contribution.abs() / total_abs if total_abs else 0.0
    return frame


def removal_robustness(result) -> pd.DataFrame:
    ending = float(result.daily.equity.iloc[-1])
    initial = result.config.initial_cash
    years = len(result.daily.loc[result.active_start:]) / 252 if result.active_start is not None else len(result.daily) / 252
    ordered = result.contributions.sort_values(ascending=False)
    rows = []
    for count in (1, 3):
        removed = float(ordered.head(count).sum())
        adjusted = ending - removed
        rows.append({
            "removed_contributors": count, "removed_pnl": removed,
            "approximate_ending_equity": adjusted,
            "approximate_cagr": (adjusted / initial) ** (1 / years) - 1 if adjusted > 0 else -1,
        })
    return pd.DataFrame(rows)

