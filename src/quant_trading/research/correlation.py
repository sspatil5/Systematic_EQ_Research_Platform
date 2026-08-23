"""Mean daily cross-sectional correlation between candidate signals."""

from __future__ import annotations

import numpy as np
import pandas as pd


def signal_correlation_matrix(
    dataset: pd.DataFrame,
    signals: tuple[str, ...],
    *,
    minimum_cross_section: int = 20,
) -> pd.DataFrame:
    accumulators: dict[tuple[str, str], list[float]] = {
        (left, right): [] for left in signals for right in signals
    }
    for _, cross_section in dataset[list(signals)].groupby(level="date", sort=False):
        correlations = cross_section.corr(method="spearman", min_periods=minimum_cross_section)
        for pair in accumulators:
            value = correlations.loc[pair] if pair[0] in correlations and pair[1] in correlations else np.nan
            if pd.notna(value):
                accumulators[pair].append(float(value))
    result = pd.DataFrame(index=signals, columns=signals, dtype=float)
    for pair, values in accumulators.items():
        result.loc[pair[0], pair[1]] = np.mean(values) if values else np.nan
    return result


def highly_correlated_pairs(matrix: pd.DataFrame, threshold: float = 0.80) -> pd.DataFrame:
    rows = []
    for left_index, left in enumerate(matrix.columns):
        for right in matrix.columns[left_index + 1:]:
            value = matrix.loc[left, right]
            if pd.notna(value) and abs(value) > threshold:
                rows.append({"signal_a": left, "signal_b": right, "correlation": value})
    return pd.DataFrame(rows)
