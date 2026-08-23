from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_trading.features.cross_sectional import cross_sectional_zscore, percentile_rank
from quant_trading.features.market import build_market_features
from quant_trading.features.momentum import build_momentum_features
from quant_trading.features.pipeline import build_feature_dataset
from quant_trading.features.validation import validate_feature_dataset
from quant_trading.features.volatility import ANNUALIZATION_FACTOR, build_volatility_features
from quant_trading.targets import build_targets
from quant_trading.utils.config import FeatureConfig


def make_panel(prices: dict[str, list[float]], volumes: dict[str, list[float]] | None = None) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=len(next(iter(prices.values()))))
    parts = []
    for ticker, values in prices.items():
        volume = volumes[ticker] if volumes else [1_000.0] * len(values)
        part = pd.DataFrame(
            {
                "date": dates,
                "ticker": ticker,
                "open": values,
                "high": np.asarray(values) * 1.01,
                "low": np.asarray(values) * 0.99,
                "close": values,
                "volume": volume,
            }
        ).set_index(["date", "ticker"])
        parts.append(part)
    return pd.concat(parts).sort_index()


def minimal_config(**updates: object) -> FeatureConfig:
    values: dict[str, object] = {
        "enabled_groups": ("momentum",),
        "return_lookbacks": (1, 2, 5, 10, 20, 60, 120, 252),
        "moving_average_windows": (5, 10, 20, 50, 100, 200),
        "volatility_windows": (5, 10, 20, 60),
        "target_horizons": (1, 5, 10, 20),
        "rank_target_horizons": (5,),
        "excess_target_horizons": (5,),
        "cross_sectional_features": ("ret_20d",),
        "cross_sectional_transforms": ("rank", "zscore"),
    }
    values.update(updates)
    return FeatureConfig(**values)


def test_trailing_returns_are_exact() -> None:
    panel = make_panel({"AAA": [100.0, 110.0, 121.0]})
    result = build_momentum_features(panel, (1, 2), (2,))
    aaa = result.xs("AAA", level="ticker")
    assert aaa["ret_1d"].iloc[1] == pytest.approx(0.10)
    assert aaa["ret_1d"].iloc[2] == pytest.approx(0.10)
    assert aaa["ret_2d"].iloc[2] == pytest.approx(0.21)


def test_future_target_shift_is_forward_and_endpoint_is_missing() -> None:
    panel = make_panel({"AAA": [100.0, 110.0, 121.0]})
    target = build_targets(
        panel, (1,), rank_horizons=(), excess_horizons=()
    ).xs("AAA", level="ticker")["target_return_1d"]
    assert target.iloc[0] == pytest.approx(0.10)
    assert target.iloc[1] == pytest.approx(0.10)
    assert pd.isna(target.iloc[2])


def test_last_h_target_observations_are_missing_per_security() -> None:
    panel = make_panel({"AAA": list(range(100, 110)), "BBB": list(range(200, 210))})
    targets = build_targets(panel, (5,), rank_horizons=(), excess_horizons=())
    for ticker in ("AAA", "BBB"):
        values = targets.xs(ticker, level="ticker")["target_return_5d"]
        assert values.iloc[-5:].isna().all()
        assert values.iloc[:-5].notna().all()


def test_cross_sectional_rank_values_and_ties() -> None:
    panel = make_panel({"AAA": [1.0], "BBB": [2.0], "CCC": [2.0]})
    values = panel["close"]
    ranked = percentile_rank(values)
    date = panel.index.get_level_values("date")[0]
    assert ranked.loc[(date, "AAA")] == pytest.approx(1 / 3)
    assert ranked.loc[(date, "BBB")] == pytest.approx(5 / 6)
    assert ranked.loc[(date, "CCC")] == pytest.approx(5 / 6)


def test_cross_sectional_transforms_are_date_isolated() -> None:
    panel = make_panel({"AAA": [1.0, 1000.0], "BBB": [2.0, -1000.0], "CCC": [3.0, 0.0]})
    original = percentile_rank(panel["close"])
    changed = panel["close"].copy()
    second_date = panel.index.get_level_values("date").unique()[1]
    changed.loc[(second_date, slice(None))] *= -999
    recalculated = percentile_rank(changed)
    first_date = panel.index.get_level_values("date").unique()[0]
    pd.testing.assert_series_equal(
        original.xs(first_date, level="date"), recalculated.xs(first_date, level="date")
    )


def test_constant_cross_section_has_undefined_zscore() -> None:
    panel = make_panel({"AAA": [3.0], "BBB": [3.0]})
    assert cross_sectional_zscore(panel["close"]).isna().all()


def test_realized_volatility_matches_sample_standard_deviation() -> None:
    returns = pd.Series([np.nan, 0.01, -0.02, 0.03, -0.01, 0.02])
    prices = 100 * (1 + returns.fillna(0)).cumprod()
    panel = make_panel({"AAA": prices.tolist()})
    daily = panel["close"].groupby(level="ticker").pct_change(fill_method=None)
    result = build_volatility_features(daily, (5, 20, 60))
    expected = np.std([0.01, -0.02, 0.03, -0.01, 0.02], ddof=1) * ANNUALIZATION_FACTOR
    assert result.xs("AAA", level="ticker")["realized_vol_5"].iloc[-1] == pytest.approx(expected)


def test_beta_is_two_for_asset_with_twice_market_returns() -> None:
    market_returns = np.array([0.005, -0.01, 0.015, 0.002, -0.004] * 15)
    market_prices = 100 * np.cumprod(1 + market_returns)
    asset_prices = 50 * np.cumprod(1 + 2 * market_returns)
    panel = make_panel({"AAA": asset_prices.tolist(), "SPY": market_prices.tolist()})
    daily = panel["close"].groupby(level="ticker").pct_change(fill_method=None)
    features = build_market_features(panel, daily, "SPY")
    beta = features.xs("AAA", level="ticker")["beta_20"].dropna()
    assert len(beta) > 0
    assert beta.iloc[-1] == pytest.approx(2.0, abs=1e-10)


def test_new_ticker_has_no_long_lookback_feature() -> None:
    panel = make_panel({"AAA": np.linspace(100, 200, 300).tolist()})
    dates = panel.index.get_level_values("date").unique()
    new_rows = make_panel({"NEW": np.linspace(20, 21, 10).tolist()})
    new_rows = new_rows.reset_index()
    new_rows["date"] = dates[-10:]
    panel = pd.concat([panel, new_rows.set_index(["date", "ticker"])]).sort_index()
    features = build_momentum_features(panel, (252,), (200,))
    assert features.xs("NEW", level="ticker")["ret_252d"].isna().all()
    assert features.xs("NEW", level="ticker")["price_to_sma_200"].isna().all()


def test_future_mutation_cannot_change_features_through_cutoff() -> None:
    count = 300
    base = make_panel({
        "AAA": np.linspace(80, 130, count).tolist(),
        "BBB": np.linspace(150, 90, count).tolist(),
        "SPY": np.linspace(100, 140, count).tolist(),
    })
    changed = base.copy()
    dates = base.index.get_level_values("date").unique()
    cutoff = dates[269]
    future = changed.index.get_level_values("date") > cutoff
    changed.loc[future, "close"] *= np.linspace(0.1, 10.0, future.sum())
    config = FeatureConfig()
    first = build_feature_dataset(base, config)
    second = build_feature_dataset(changed, config)
    past = first.data.index.get_level_values("date") <= cutoff
    pd.testing.assert_frame_equal(
        first.data.loc[past, list(first.feature_columns)],
        second.data.loc[past, list(second.feature_columns)],
    )
    assert not first.data.loc[past, "target_return_20d"].equals(
        second.data.loc[past, "target_return_20d"]
    )


def test_pipeline_does_not_mutate_input_and_metadata_is_queryable() -> None:
    panel = make_panel({
        "AAA": np.linspace(80, 130, 300).tolist(),
        "BBB": np.linspace(90, 150, 300).tolist(),
        "SPY": np.linspace(100, 140, 300).tolist(),
    })
    before = panel.copy(deep=True)
    result = build_feature_dataset(panel, FeatureConfig())
    pd.testing.assert_frame_equal(panel, before)
    assert result.metadata["ret_20d"].formula == "close[t] / close[t-20] - 1"
    assert result.metadata["ret_20d_rank"].cross_sectional is True
    assert set(result.feature_columns).issubset(result.metadata)
    assert result.summary.number_of_rows == len(panel)
    assert not set(result.feature_columns) & set(result.target_columns)


def test_missing_benchmark_fails_loudly() -> None:
    panel = make_panel({"AAA": np.linspace(100, 120, 70).tolist()})
    with pytest.raises(ValueError, match="benchmark 'SPY' is absent"):
        build_market_features(
            panel,
            panel["close"].groupby(level="ticker").pct_change(fill_method=None),
        )


def test_validation_rejects_infinity_and_bad_rank() -> None:
    panel = make_panel({"AAA": [100.0], "SPY": [100.0]})
    dataset = pd.DataFrame(
        {"signal_rank": [1.2, np.inf], "target_return_1d": [0.1, np.nan]},
        index=panel.index,
    )
    with pytest.raises(ValueError, match="infinite"):
        validate_feature_dataset(
            dataset,
            expected_index=panel.index,
            feature_columns=("signal_rank",),
            target_columns=("target_return_1d",),
        )
