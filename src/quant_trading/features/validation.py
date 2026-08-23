"""Structural validation and summaries for feature datasets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re

import numpy as np
import pandas as pd

VALID_COLUMN = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_feature_dataset(
    dataset: pd.DataFrame,
    *,
    expected_index: pd.MultiIndex,
    feature_columns: tuple[str, ...],
    target_columns: tuple[str, ...],
) -> None:
    if not dataset.index.equals(expected_index):
        raise ValueError("Feature pipeline changed row count, ordering, or index values")
    if dataset.index.has_duplicates:
        raise ValueError("Feature dataset contains duplicate rows")
    if set(feature_columns) & set(target_columns):
        raise ValueError("A target column was included in feature inputs")
    if any(name.startswith("target_") for name in feature_columns):
        raise ValueError("Feature inputs may not use target_-prefixed columns")
    invalid_names = [name for name in dataset.columns if not VALID_COLUMN.fullmatch(name)]
    if invalid_names:
        raise ValueError(f"Invalid column names: {invalid_names}")
    numeric = dataset.select_dtypes(include=[np.number])
    if np.isinf(numeric.to_numpy()).any():
        raise ValueError("Feature dataset contains infinite values")
    for name in dataset.columns:
        if name.endswith("_rank"):
            valid = dataset[name].dropna()
            if not valid.between(0.0, 1.0).all():
                raise ValueError(f"Rank {name} contains values outside [0, 1]")


@dataclass(frozen=True)
class DatasetSummary:
    number_of_dates: int
    number_of_securities: int
    number_of_rows: int
    number_of_features: int
    number_of_targets: int
    earliest_date: str
    latest_date: str
    missing_percentage_by_feature: dict[str, float]
    infinite_values: int
    primary_target_observations: int
    complete_feature_observations: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def summarize_dataset(
    dataset: pd.DataFrame,
    feature_columns: tuple[str, ...],
    target_columns: tuple[str, ...],
    primary_target: str,
) -> DatasetSummary:
    dates = dataset.index.get_level_values("date")
    numeric = dataset.select_dtypes(include=[np.number])
    return DatasetSummary(
        number_of_dates=dates.nunique(),
        number_of_securities=dataset.index.get_level_values("ticker").nunique(),
        number_of_rows=len(dataset),
        number_of_features=len(feature_columns),
        number_of_targets=len(target_columns),
        earliest_date=str(dates.min().date()),
        latest_date=str(dates.max().date()),
        missing_percentage_by_feature={
            column: round(float(dataset[column].isna().mean() * 100), 4)
            for column in feature_columns
        },
        infinite_values=int(np.isinf(numeric.to_numpy()).sum()),
        primary_target_observations=int(dataset[primary_target].notna().sum()),
        complete_feature_observations=int(dataset[list(feature_columns)].notna().all(axis=1).sum()),
    )
