"""Date-isolated cross-sectional transforms."""

from __future__ import annotations

import numpy as np
import pandas as pd


def percentile_rank(series: pd.Series, *, min_observations: int = 2) -> pd.Series:
    """Average-tie percentile rank in [0, 1], calculated independently per date."""
    def rank_date(values: pd.Series) -> pd.Series:
        if values.notna().sum() < min_observations:
            return pd.Series(np.nan, index=values.index)
        return values.rank(method="average", pct=True)

    return series.groupby(level="date", group_keys=False, sort=False).apply(rank_date)


def cross_sectional_zscore(series: pd.Series, *, min_observations: int = 2) -> pd.Series:
    """Sample z-score by date; undefined constant or undersized cross-sections remain NaN."""
    def zscore_date(values: pd.Series) -> pd.Series:
        valid = values.dropna()
        if len(valid) < min_observations:
            return pd.Series(np.nan, index=values.index)
        std = valid.std(ddof=1)
        if pd.isna(std) or std == 0:
            return pd.Series(np.nan, index=values.index)
        return (values - valid.mean()) / std

    return series.groupby(level="date", group_keys=False, sort=False).apply(zscore_date)


def apply_cross_sectional_transforms(
    features: pd.DataFrame,
    columns: tuple[str, ...],
    transforms: tuple[str, ...],
    *,
    min_observations: int = 2,
) -> pd.DataFrame:
    output = pd.DataFrame(index=features.index)
    for column in columns:
        if column not in features:
            raise ValueError(f"Cross-sectional source feature {column!r} is unavailable")
        if "rank" in transforms:
            output[f"{column}_rank"] = percentile_rank(
                features[column], min_observations=min_observations
            )
        if "zscore" in transforms:
            output[f"{column}_cs_zscore"] = cross_sectional_zscore(
                features[column], min_observations=min_observations
            )
    unknown = set(transforms) - {"rank", "zscore"}
    if unknown:
        raise ValueError(f"Unknown cross-sectional transforms: {sorted(unknown)}")
    return output

