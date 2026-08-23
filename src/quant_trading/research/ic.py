"""Daily cross-sectional information coefficients and robust inference."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class ICInference:
    valid_dates: int
    mean: float
    median: float
    standard_deviation: float
    information_ratio: float
    positive_percentage: float
    negative_percentage: float
    standard_error: float
    naive_t_stat: float
    naive_p_value: float
    hac_standard_error: float
    hac_t_stat: float
    hac_p_value: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def daily_information_coefficients(
    dataset: pd.DataFrame,
    signal: str,
    target: str,
    *,
    minimum_cross_section: int = 20,
) -> pd.DataFrame:
    """Calculate Pearson and Spearman correlations independently on every date."""
    if signal.startswith("target_"):
        raise ValueError("Target columns cannot be analyzed as candidate signals")
    missing = {signal, target} - set(dataset.columns)
    if missing:
        raise ValueError(f"Dataset is missing columns: {sorted(missing)}")
    rows: list[dict[str, object]] = []
    for date, cross_section in dataset[[signal, target]].groupby(level="date", sort=True):
        valid = cross_section.dropna()
        if len(valid) < minimum_cross_section:
            continue
        x, y = valid[signal], valid[target]
        if x.nunique() < 2 or y.nunique() < 2:
            continue
        rows.append({
            "date": date,
            "pearson_ic": float(stats.pearsonr(x, y).statistic),
            "spearman_ic": float(stats.spearmanr(x, y).statistic),
            "securities": len(valid),
        })
    if not rows:
        return pd.DataFrame(columns=["pearson_ic", "spearman_ic", "securities"]).rename_axis("date")
    return pd.DataFrame(rows).set_index("date")


def _two_sided_t_pvalue(value: float, degrees_of_freedom: int) -> float:
    return float(2 * stats.t.sf(abs(value), degrees_of_freedom)) if np.isfinite(value) else np.nan


def hac_standard_error_of_mean(values: pd.Series, lags: int) -> float:
    """Newey-West standard error of a sample mean using Bartlett weights."""
    clean = values.dropna().astype(float).to_numpy()
    n = len(clean)
    if n < 2 or lags < 0:
        return np.nan
    lags = min(lags, n - 1)
    demeaned = clean - clean.mean()
    long_run_variance = float(np.dot(demeaned, demeaned) / n)
    for lag in range(1, lags + 1):
        covariance = float(np.dot(demeaned[lag:], demeaned[:-lag]) / n)
        long_run_variance += 2.0 * (1.0 - lag / (lags + 1.0)) * covariance
    return math.sqrt(max(long_run_variance, 0.0) / n)


def infer_ic(values: pd.Series, *, hac_lags: int = 4) -> ICInference:
    clean = values.dropna().astype(float)
    n = len(clean)
    if n < 2:
        nan = float("nan")
        return ICInference(n, nan, nan, nan, nan, nan, nan, nan, nan, nan, nan, nan, nan)
    mean = float(clean.mean())
    std = float(clean.std(ddof=1))
    standard_error = std / math.sqrt(n)
    naive_t = mean / standard_error if standard_error > 0 else np.nan
    hac_se = hac_standard_error_of_mean(clean, hac_lags)
    hac_t = mean / hac_se if hac_se > 0 else np.nan
    return ICInference(
        n, mean, float(clean.median()), std, mean / std if std > 0 else np.nan,
        float((clean > 0).mean()), float((clean < 0).mean()), standard_error,
        naive_t, _two_sided_t_pvalue(naive_t, n - 1), hac_se, hac_t,
        _two_sided_t_pvalue(hac_t, n - 1),
    )


def non_overlapping_inference(
    daily_ic: pd.Series, horizon: int, *, hac_lags: int = 0
) -> pd.DataFrame:
    """Report every offset; never select an offset based on its result."""
    ordered = daily_ic.dropna().sort_index()
    rows = []
    for offset in range(horizon):
        inference = infer_ic(ordered.iloc[offset::horizon], hac_lags=hac_lags)
        rows.append({"offset": offset, **inference.to_dict()})
    return pd.DataFrame(rows).set_index("offset")

