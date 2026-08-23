"""Cross-sectional ranking persistence and membership turnover."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_trading.research.quantiles import assign_quantiles


def membership_turnover(current: set[str], previous: set[str]) -> float:
    """Fraction of current members absent from the previous set."""
    return len(current - previous) / len(current) if current else np.nan


def signal_turnover(
    dataset: pd.DataFrame,
    signal: str,
    *,
    quantiles: int = 5,
    rebalance_step: int = 1,
) -> pd.DataFrame:
    dates = dataset.index.get_level_values("date").unique().sort_values()[::rebalance_step]
    prior_ranks: pd.Series | None = None
    prior_top: set[str] = set()
    prior_bottom: set[str] = set()
    rows = []
    for date in dates:
        values = dataset.xs(date, level="date")[signal].dropna()
        groups = assign_quantiles(values, quantiles)
        ranks = values.rank(method="average", pct=True)
        top = set(groups[groups == quantiles].index)
        bottom = set(groups[groups == 1].index)
        if prior_ranks is not None:
            paired = pd.concat([prior_ranks, ranks], axis=1).dropna()
            rank_corr = paired.iloc[:, 0].corr(paired.iloc[:, 1], method="spearman") if len(paired) >= 2 else np.nan
            rows.append({
                "date": date,
                "rank_autocorrelation": rank_corr,
                "top_turnover": membership_turnover(top, prior_top),
                "bottom_turnover": membership_turnover(bottom, prior_bottom),
            })
        prior_ranks, prior_top, prior_bottom = ranks, top, bottom
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()

