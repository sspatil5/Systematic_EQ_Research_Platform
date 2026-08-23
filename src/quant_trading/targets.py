"""Forward adjusted-close targets, kept separate from feature construction."""

from __future__ import annotations

import pandas as pd

from quant_trading.features.common import by_ticker
from quant_trading.features.cross_sectional import percentile_rank


def build_targets(
    panel: pd.DataFrame,
    horizons: tuple[int, ...] = (1, 5, 10, 20),
    *,
    benchmark: str = "SPY",
    rank_horizons: tuple[int, ...] = (5,),
    excess_horizons: tuple[int, ...] = (5,),
    min_cross_sectional_observations: int = 2,
) -> pd.DataFrame:
    close = panel["close"].astype(float)
    output = pd.DataFrame(index=panel.index)
    for days in horizons:
        output[f"target_return_{days}d"] = by_ticker(close).shift(-days) / close - 1.0

    dates = panel.index.get_level_values("date")
    for days in rank_horizons:
        source = f"target_return_{days}d"
        if source not in output:
            raise ValueError(f"Rank target horizon {days} is not in target_horizons")
        output[f"{source}_rank"] = percentile_rank(
            output[source], min_observations=min_cross_sectional_observations
        )
    if excess_horizons:
        if benchmark not in set(panel.index.get_level_values("ticker")):
            raise ValueError(f"Target benchmark {benchmark!r} is absent from the panel")
        benchmark_close = panel.xs(benchmark, level="ticker")["close"].astype(float)
        for days in excess_horizons:
            source = f"target_return_{days}d"
            if source not in output:
                raise ValueError(f"Excess target horizon {days} is not in target_horizons")
            benchmark_future = benchmark_close.shift(-days) / benchmark_close - 1.0
            aligned = pd.Series(dates.map(benchmark_future), index=panel.index, dtype=float)
            output[f"target_excess_return_{days}d"] = output[source] - aligned
    return output

