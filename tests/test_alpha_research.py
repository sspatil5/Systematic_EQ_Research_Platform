from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_trading.alpha_research.diagnostics import long_only_diagnostics, orthogonality_table
from quant_trading.alpha_research.fama_macbeth import (
    RegressionSpecification, daily_cross_sectional_regression, summarize_coefficients,
)
from quant_trading.alpha_research.features import (
    build_momentum_expansion, decompose_daily_returns, idiosyncratic_volatility_60,
)
from quant_trading.alpha_research.split import split_development_confirmation
from quant_trading.alpha_research.transforms import (
    equal_weight_combination, residualize_cross_sectionally, sector_neutral_zscore,
)


def index(days: int, tickers: tuple[str, ...]) -> pd.MultiIndex:
    return pd.MultiIndex.from_product(
        [pd.bdate_range("2020-01-01", periods=days), tickers], names=["date", "ticker"]
    )


def test_sector_neutralization_is_within_date_and_sector() -> None:
    idx = index(1, ("A", "B", "C", "D", "E", "F"))
    signal = pd.Series([1, 2, 3, 10, 20, 30], index=idx, dtype=float)
    sectors = pd.Series(["X"] * 3 + ["Y"] * 3, index=idx)
    result = sector_neutral_zscore(signal, sectors, minimum_group=3)
    grouped = result.groupby(sectors)
    assert grouped.mean().abs().max() < 1e-12
    assert grouped.std().sub(1).abs().max() < 1e-12


def test_cross_sectional_residualization_removes_linear_control() -> None:
    idx = index(2, tuple("ABCDE"))
    control = pd.Series(np.tile(np.arange(5), 2), index=idx, dtype=float)
    signal = 3 * control + np.tile([1, -1, 0, 1, -1], 2)
    residual = residualize_cross_sectionally(
        signal, pd.DataFrame({"control": control}), minimum_observations=5
    )
    for _, values in pd.concat([residual, control], axis=1).groupby(level="date"):
        assert abs(values.iloc[:, 0].corr(values.iloc[:, 1])) < 1e-12


def test_fama_macbeth_recovers_known_coefficient() -> None:
    idx = index(40, tuple(f"S{i:02d}" for i in range(30)))
    rng = np.random.default_rng(3)
    x = pd.Series(rng.normal(size=len(idx)), index=idx)
    # x is nearly unit variance cross-sectionally, so standardized coefficient is near 0.02.
    data = pd.DataFrame({"x": x, "target": 0.02 * x}, index=idx)
    spec = RegressionSpecification("known", ("x",))
    daily = daily_cross_sectional_regression(data, "target", spec, minimum_observations=20)
    assert daily["x"].mean() == pytest.approx(0.02, abs=0.005)
    summary = summarize_coefficients(daily, spec)
    assert summary.loc[0, "mean_coefficient"] > 0


def test_residualization_cannot_use_future_cross_sections() -> None:
    idx = index(6, tuple(f"S{i}" for i in range(8)))
    rng = np.random.default_rng(4)
    signal = pd.Series(rng.normal(size=len(idx)), index=idx)
    control = pd.Series(rng.normal(size=len(idx)), index=idx)
    first = residualize_cross_sectionally(signal, control.to_frame("c"), minimum_observations=8)
    changed = control.copy()
    cutoff = idx.get_level_values("date").unique()[3]
    changed.loc[changed.index.get_level_values("date") > cutoff] *= 1000
    second = residualize_cross_sectionally(signal, changed.to_frame("c"), minimum_observations=8)
    pd.testing.assert_series_equal(first.loc[:cutoff], second.loc[:cutoff])


def test_momentum_variants_and_risk_adjustment_formulas() -> None:
    days = 260
    idx = index(days, ("AAA",))
    close = pd.Series(np.arange(100, 100 + days, dtype=float), index=idx)
    panel = pd.DataFrame({"close": close}, index=idx)
    existing = pd.DataFrame({"realized_vol_60": 0.5}, index=idx)
    result = build_momentum_expansion(panel, existing)
    end = result.iloc[-1]
    prices = close.droplevel("ticker")
    assert end.momentum_6_1 == pytest.approx(prices.iloc[-22] / prices.iloc[-127] - 1)
    assert end.momentum_9_1 == pytest.approx(prices.iloc[-22] / prices.iloc[-190] - 1)
    assert end.momentum_12_1 == pytest.approx(prices.iloc[-22] / prices.iloc[-253] - 1)
    assert end.momentum_12_2 == pytest.approx(prices.iloc[-43] / prices.iloc[-253] - 1)
    assert end.risk_adjusted_momentum_12_1 == pytest.approx(end.momentum_12_1 / 0.5)


def test_idiosyncratic_volatility_is_zero_for_exact_market_multiple() -> None:
    days = 80
    market_returns = np.array([0.01, -0.005, 0.002, 0.007] * 20)
    frames = []
    for ticker, multiplier in (("SPY", 1.0), ("AAA", 2.0)):
        idx = index(days, (ticker,))
        frames.append(pd.DataFrame({
            "ret_1d": multiplier * market_returns,
            "market_return_1d": market_returns,
        }, index=idx))
    data = pd.concat(frames).sort_index()
    result = idiosyncratic_volatility_60(data).xs("AAA", level="ticker").dropna()
    assert result.iloc[-1] == pytest.approx(0.0, abs=1e-8)


def test_development_confirmation_are_disjoint_and_confirmation_cannot_change_development() -> None:
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2021-12-30", "2021-12-31", "2022-01-03"]), ["A", "B"]],
        names=["date", "ticker"],
    )
    data = pd.DataFrame({"x": np.arange(len(idx))}, index=idx)
    development, confirmation = split_development_confirmation(data)
    assert development.index.get_level_values("date").max() == pd.Timestamp("2021-12-31")
    assert confirmation.index.get_level_values("date").min() == pd.Timestamp("2022-01-03")
    changed = data.copy(); changed.loc[confirmation.index, "x"] = 999
    changed_development, _ = split_development_confirmation(changed)
    pd.testing.assert_frame_equal(development, changed_development)


def test_hypotheses_were_registered_before_evaluation() -> None:
    registry = pd.read_csv(Path("reports/phase3_5/hypothesis_registry.csv"))
    assert len(registry) == 13
    assert registry["hypothesis_id"].is_unique
    assert set(registry["development_period"]) == {"2010-01-01/2021-12-31"}


def test_overnight_intraday_decomposition_and_no_future_leakage() -> None:
    idx = index(4, ("AAA",))
    panel = pd.DataFrame({
        "open": [100, 103, 105, 108], "close": [102, 104, 107, 109]
    }, index=idx, dtype=float)
    first = decompose_daily_returns(panel)
    expected_overnight = 103 / 102 - 1
    assert first.iloc[1].overnight_return_1d == pytest.approx(expected_overnight)
    assert first.iloc[1].intraday_return_1d == pytest.approx(104 / 103 - 1)
    changed = panel.copy(); changed.iloc[-1] *= 10
    second = decompose_daily_returns(changed)
    pd.testing.assert_frame_equal(first.iloc[:-1], second.iloc[:-1])


def test_equal_weight_combination_has_no_fitted_weights() -> None:
    idx = index(1, tuple("ABCDE"))
    components = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [5, 1, 4, 2, 3]}, index=idx)
    combined = equal_weight_combination(components)
    expected = ((components - components.mean()) / components.std(ddof=1)).mean(axis=1)
    pd.testing.assert_series_equal(combined, expected)


def test_orthogonality_handles_signal_equal_to_reference_exposure() -> None:
    idx = index(2, tuple(f"S{i:02d}" for i in range(20)))
    values = np.tile(np.arange(20, dtype=float), 2)
    data = pd.DataFrame({
        "momentum_12_1": values, "realized_vol_20": values[::-1],
        "beta_20": values * 0.5, "avg_dollar_volume_20": values + 1,
    }, index=idx)
    result = orthogonality_table(data, ("momentum_12_1",))
    assert result.loc[0, "correlation_momentum"] == 1.0


def test_long_only_diagnostics_identify_useful_top_quantile() -> None:
    idx = index(10, tuple(["SPY"] + [f"S{i:02d}" for i in range(24)]))
    signal = np.tile(np.arange(25), 10)
    data = pd.DataFrame({"signal": signal, "target_return_5d": signal / 1000}, index=idx)
    result = long_only_diagnostics(data, "signal")
    assert result["selected_minus_universe"] > 0
    assert result["opposite_minus_universe"] < 0


def test_synthetic_beta_confound_disappears_but_true_momentum_survives() -> None:
    rng = np.random.default_rng(8)
    tickers = tuple(f"S{i:02d}" for i in range(60))
    idx = index(100, tickers)
    beta = pd.Series(rng.normal(size=len(idx)), index=idx)
    momentum = pd.Series(rng.normal(size=len(idx)), index=idx)
    volatility = beta + pd.Series(rng.normal(scale=0.05, size=len(idx)), index=idx)
    target = 0.02 * momentum + 0.03 * beta + rng.normal(scale=0.01, size=len(idx))
    data = pd.DataFrame({
        "target": target, "momentum": momentum, "beta": beta, "volatility": volatility,
    }, index=idx)
    raw = daily_cross_sectional_regression(
        data, "target", RegressionSpecification("raw", ("volatility",)), minimum_observations=30
    )
    controlled = daily_cross_sectional_regression(
        data, "target", RegressionSpecification("controlled", ("volatility", "beta", "momentum")),
        minimum_observations=30,
    )
    assert raw["volatility"].mean() > 0.02
    assert abs(controlled["volatility"].mean()) < 0.005
    assert controlled["momentum"].mean() > 0.015
