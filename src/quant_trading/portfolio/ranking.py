"""Frozen Phase 4 signal selection."""

from __future__ import annotations

import pandas as pd

APPROVED_SIGNALS = (
    "sector_neutral_momentum_12_1",
    "combined_momentum_volatility",
    "momentum_12_1",  # benchmark only
)


def validate_signal(signal: str) -> None:
    if signal not in APPROVED_SIGNALS:
        raise ValueError(f"Signal {signal!r} is not approved for Phase 4")


def select_top(
    cross_section: pd.DataFrame,
    signal: str,
    top_n: int,
    *,
    liquidity_floor: float,
) -> pd.DataFrame:
    validate_signal(signal)
    valid = cross_section.dropna(subset=[signal, "avg_dollar_volume_20"])
    valid = valid[valid["avg_dollar_volume_20"] >= liquidity_floor]
    ranked = valid.sort_values([signal], ascending=False).copy()
    ranked["rank"] = ranked[signal].rank(method="first", ascending=False).astype(int)
    return ranked.head(top_n)

