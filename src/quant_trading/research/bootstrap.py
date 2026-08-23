"""Dependence-aware moving-block bootstrap."""

from __future__ import annotations

import numpy as np
import pandas as pd


def block_bootstrap_mean_ci(
    values: pd.Series,
    *,
    iterations: int = 1000,
    block_length: int = 20,
    seed: int = 42,
    confidence: float = 0.95,
) -> tuple[float, float]:
    clean = values.dropna().astype(float).to_numpy()
    n = len(clean)
    if n == 0 or iterations <= 0 or block_length <= 0:
        return np.nan, np.nan
    block_length = min(block_length, n)
    starts = np.arange(0, n - block_length + 1)
    rng = np.random.default_rng(seed)
    estimates = np.empty(iterations)
    block_count = int(np.ceil(n / block_length))
    for iteration in range(iterations):
        selected = rng.choice(starts, size=block_count, replace=True)
        sample = np.concatenate([clean[start:start + block_length] for start in selected])[:n]
        estimates[iteration] = sample.mean()
    alpha = (1.0 - confidence) / 2.0
    return tuple(float(value) for value in np.quantile(estimates, [alpha, 1 - alpha]))

