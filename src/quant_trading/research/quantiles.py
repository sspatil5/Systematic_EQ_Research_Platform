"""Forward-return research quantiles; these are not executable P&L."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class QuantileSummary:
    returns: dict[int, float]
    q5_minus_q1: float
    quantile_rank_correlation: float
    adjacent_fraction_expected: float


def assign_quantiles(values: pd.Series, quantiles: int = 5) -> pd.Series:
    """Assign near-equal groups after stable average-tie ranking; labels run 1..Q."""
    valid = values.dropna()
    result = pd.Series(pd.NA, index=values.index, dtype="Int64")
    if len(valid) < quantiles or valid.nunique() < 2:
        return result
    percentiles = valid.rank(method="average", pct=True)
    labels = np.minimum(np.ceil(percentiles * quantiles), quantiles).astype(int)
    result.loc[valid.index] = labels
    return result


def quantile_return_series(
    dataset: pd.DataFrame,
    signal: str,
    target: str,
    *,
    quantiles: int = 5,
    minimum_cross_section: int = 20,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for date, cross_section in dataset[[signal, target]].groupby(level="date", sort=True):
        valid = cross_section.dropna()
        if len(valid) < max(minimum_cross_section, quantiles):
            continue
        groups = assign_quantiles(valid[signal], quantiles)
        means = valid[target].groupby(groups).mean()
        if len(means) != quantiles:
            continue
        row: dict[str, object] = {"date": date}
        row.update({f"q{q}": float(means.loc[q]) for q in range(1, quantiles + 1)})
        row["q_high_minus_low"] = row[f"q{quantiles}"] - row["q1"]
        rows.append(row)
    if not rows:
        return pd.DataFrame().rename_axis("date")
    return pd.DataFrame(rows).set_index("date")


def summarize_quantiles(series: pd.DataFrame, expected_direction: int = 0) -> QuantileSummary:
    q_columns = [column for column in series if column.startswith("q") and column[1:].isdigit()]
    averages = {int(column[1:]): float(series[column].mean()) for column in q_columns}
    if not averages:
        return QuantileSummary({}, np.nan, np.nan, np.nan)
    ordered = np.array([averages[q] for q in sorted(averages)])
    correlation = float(stats.spearmanr(np.arange(1, len(ordered) + 1), ordered).statistic)
    differences = np.diff(ordered)
    direction = expected_direction if expected_direction in (-1, 1) else 1
    adjacent = float((differences * direction > 0).mean()) if len(differences) else np.nan
    return QuantileSummary(
        averages, float(ordered[-1] - ordered[0]), correlation, adjacent
    )

