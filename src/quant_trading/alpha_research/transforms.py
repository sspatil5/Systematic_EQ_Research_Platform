"""Contemporaneous cross-sectional neutralization without future-return fitting."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sector_neutral_zscore(
    signal: pd.Series, sectors: pd.Series, *, minimum_group: int = 3
) -> pd.Series:
    frame = pd.DataFrame({"signal": signal, "sector": sectors})
    grouped = frame.groupby([frame.index.get_level_values("date"), "sector"])["signal"]
    count = grouped.transform("count")
    mean = grouped.transform("mean")
    std = grouped.transform("std").replace(0.0, np.nan)
    result = (signal - mean) / std
    return result.where(count >= minimum_group)


def cross_sectional_zscore(series: pd.Series, minimum: int = 3) -> pd.Series:
    grouped = series.groupby(level="date")
    count = grouped.transform("count")
    std = grouped.transform("std").replace(0.0, np.nan)
    return ((series - grouped.transform("mean")) / std).where(count >= minimum)


def residualize_cross_sectionally(
    signal: pd.Series,
    controls: pd.DataFrame,
    *,
    sectors: pd.Series | None = None,
    minimum_observations: int = 20,
) -> pd.Series:
    """OLS residual by date using only contemporaneous observable features."""
    result = pd.Series(np.nan, index=signal.index, dtype=float)
    frame = pd.concat([signal.rename("signal"), controls], axis=1)
    if sectors is not None:
        frame["sector"] = sectors
    for _, cross in frame.groupby(level="date", sort=False):
        numeric = ["signal", *controls.columns]
        valid = cross.dropna(subset=numeric)
        if len(valid) < max(minimum_observations, len(controls.columns) + 2):
            continue
        x = valid[list(controls.columns)].astype(float)
        x = (x - x.mean()) / x.std(ddof=1).replace(0.0, np.nan)
        if sectors is not None:
            dummies = pd.get_dummies(valid["sector"], drop_first=True, dtype=float)
            x = pd.concat([x, dummies], axis=1)
        x.insert(0, "intercept", 1.0)
        good = x.notna().all(axis=1)
        if good.sum() < x.shape[1] + 1:
            continue
        y = valid.loc[good, "signal"].astype(float)
        matrix = x.loc[good].to_numpy(float)
        coefficients = np.linalg.lstsq(matrix, y.to_numpy(), rcond=None)[0]
        result.loc[y.index] = y.to_numpy() - matrix @ coefficients
    return result


def equal_weight_combination(components: pd.DataFrame) -> pd.Series:
    """Equal-weight date-standardized components; no fitted or optimized weights."""
    standardized = pd.DataFrame(
        {column: cross_sectional_zscore(components[column]) for column in components},
        index=components.index,
    )
    return standardized.mean(axis=1, skipna=False)

