"""Quantify the Phase 2 observed-row horizon limitation without changing semantics."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CalendarAudit:
    master_dates: int
    securities: int
    expected_ticker_dates: int
    observed_ticker_dates: int
    missing_ticker_dates: int
    missing_ticker_date_percentage: float
    eligible_five_row_targets: int
    five_row_targets_spanning_extra_sessions: int
    affected_target_percentage: float
    maximum_extra_sessions: int
    target_horizon_distribution: dict[int, int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def audit_panel_calendar(panel: pd.DataFrame, horizon: int = 5) -> CalendarAudit:
    dates = panel.index.get_level_values("date").unique().sort_values()
    tickers = panel.index.get_level_values("ticker").unique()
    expected = len(dates) * len(tickers)
    observed = len(panel)
    date_positions = pd.Series(np.arange(len(dates)), index=dates)
    eligible = affected = 0
    maximum_extra = 0
    horizon_distribution: dict[int, int] = {}
    for ticker in tickers:
        ticker_dates = panel.xs(ticker, level="ticker").index.sort_values()
        positions = date_positions.loc[ticker_dates].to_numpy()
        if len(positions) <= horizon:
            continue
        spans = positions[horizon:] - positions[:-horizon]
        extra = spans - horizon
        for span, count in zip(*np.unique(spans, return_counts=True), strict=True):
            horizon_distribution[int(span)] = horizon_distribution.get(int(span), 0) + int(count)
        eligible += len(extra)
        affected += int((extra > 0).sum())
        maximum_extra = max(maximum_extra, int(extra.max(initial=0)))
    missing = expected - observed
    return CalendarAudit(
        len(dates), len(tickers), expected, observed, missing,
        missing / expected if expected else np.nan, eligible, affected,
        affected / eligible if eligible else np.nan, maximum_extra,
        dict(sorted(horizon_distribution.items())),
    )
