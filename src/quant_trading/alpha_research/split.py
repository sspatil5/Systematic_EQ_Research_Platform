"""Frozen development/confirmation boundary."""

from __future__ import annotations

import pandas as pd


def split_development_confirmation(
    dataset: pd.DataFrame,
    *,
    development_end: str = "2021-12-31",
    confirmation_start: str = "2022-01-01",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = dataset.index.get_level_values("date")
    development = dataset.loc[dates <= pd.Timestamp(development_end)].copy()
    confirmation = dataset.loc[dates >= pd.Timestamp(confirmation_start)].copy()
    if set(development.index) & set(confirmation.index):
        raise ValueError("Development and confirmation samples overlap")
    return development, confirmation

