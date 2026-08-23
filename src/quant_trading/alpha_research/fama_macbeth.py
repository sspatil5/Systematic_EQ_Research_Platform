"""Daily cross-sectional regressions with HAC inference over coefficient time series."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_trading.research.ic import infer_ic


@dataclass(frozen=True)
class RegressionSpecification:
    name: str
    predictors: tuple[str, ...]
    sector_controls: bool = False


def daily_cross_sectional_regression(
    dataset: pd.DataFrame,
    target: str,
    specification: RegressionSpecification,
    *,
    sectors: pd.Series | None = None,
    minimum_observations: int = 30,
) -> pd.DataFrame:
    """Standardize continuous predictors per date and estimate OLS with an intercept."""
    columns = [target, *specification.predictors]
    frame = dataset[columns].copy()
    if specification.sector_controls:
        if sectors is None:
            raise ValueError("Sector-controlled regression requires sector labels")
        frame["sector"] = sectors
    rows = []
    for date, cross in frame.groupby(level="date", sort=True):
        valid = cross.dropna(subset=columns)
        if len(valid) < minimum_observations:
            continue
        x = valid[list(specification.predictors)].astype(float)
        std = x.std(ddof=1).replace(0.0, np.nan)
        x = (x - x.mean()) / std
        if specification.sector_controls:
            dummies = pd.get_dummies(valid["sector"], drop_first=True, dtype=float)
            x = pd.concat([x, dummies], axis=1)
        x.insert(0, "intercept", 1.0)
        good = x.notna().all(axis=1)
        if good.sum() <= x.shape[1]:
            continue
        matrix = x.loc[good].to_numpy(float)
        y = valid.loc[good, target].to_numpy(float)
        coefficients, _, rank, _ = np.linalg.lstsq(matrix, y, rcond=None)
        if rank < matrix.shape[1]:
            continue
        row: dict[str, object] = {"date": date, "observations": int(good.sum())}
        row.update(dict(zip(x.columns, coefficients, strict=True)))
        rows.append(row)
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()


def summarize_coefficients(
    coefficients: pd.DataFrame,
    specification: RegressionSpecification,
    *,
    hac_lags: int = 4,
) -> pd.DataFrame:
    rows = []
    for predictor in specification.predictors:
        inference = infer_ic(coefficients[predictor], hac_lags=hac_lags)
        rows.append({
            "model": specification.name,
            "predictor": predictor,
            "valid_dates": inference.valid_dates,
            "mean_coefficient": inference.mean,
            "standard_error": inference.standard_error,
            "naive_t_stat": inference.naive_t_stat,
            "hac_standard_error": inference.hac_standard_error,
            "hac_t_stat": inference.hac_t_stat,
            "p_value": inference.hac_p_value,
            "positive_coefficient_pct": inference.positive_percentage,
            "sector_controls": specification.sector_controls,
        })
    return pd.DataFrame(rows)

