"""Simple ex-ante SPY trend and volatility regimes."""

from __future__ import annotations

import pandas as pd


def build_market_regimes(
    dataset: pd.DataFrame,
    *,
    benchmark: str = "SPY",
    volatility_history: int = 252,
    minimum_history: int = 60,
) -> pd.DataFrame:
    if benchmark not in set(dataset.index.get_level_values("ticker")):
        raise ValueError(f"Benchmark {benchmark!r} is absent")
    required = {"price_to_sma_200", "realized_vol_20"}
    missing = required - set(dataset.columns)
    if missing:
        raise ValueError(f"Regime construction requires {sorted(missing)}")
    market = dataset.xs(benchmark, level="ticker").sort_index()
    output = pd.DataFrame(index=market.index)
    output["trend_regime"] = market["price_to_sma_200"].ge(0).map({True: "up", False: "down"})
    output.loc[market["price_to_sma_200"].isna(), "trend_regime"] = pd.NA
    # Shifted rolling median uses volatility observations available strictly before t.
    threshold = market["realized_vol_20"].shift(1).rolling(
        volatility_history, min_periods=minimum_history
    ).median()
    output["volatility_regime"] = market["realized_vol_20"].gt(threshold).map(
        {True: "high", False: "low"}
    )
    output.loc[threshold.isna() | market["realized_vol_20"].isna(), "volatility_regime"] = pd.NA
    return output


def summarize_ic_by_regime(daily_ic: pd.Series, regimes: pd.DataFrame) -> pd.DataFrame:
    joined = regimes.join(daily_ic.rename("rank_ic"), how="inner")
    rows = []
    for column in ("trend_regime", "volatility_regime"):
        for label, values in joined.dropna(subset=[column, "rank_ic"]).groupby(column):
            rows.append({
                "regime_type": column,
                "regime": label,
                "mean_rank_ic": float(values["rank_ic"].mean()),
                "valid_dates": len(values),
            })
    return pd.DataFrame(rows)

