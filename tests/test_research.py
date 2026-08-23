from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_trading.research.bootstrap import block_bootstrap_mean_ci
from quant_trading.research.calendar_audit import audit_panel_calendar
from quant_trading.research.correlation import highly_correlated_pairs, signal_correlation_matrix
from quant_trading.research.ic import (
    daily_information_coefficients,
    infer_ic,
    non_overlapping_inference,
)
from quant_trading.research.multiple_testing import adjust_pvalues
from quant_trading.research.quantiles import (
    assign_quantiles,
    quantile_return_series,
    summarize_quantiles,
)
from quant_trading.research.regimes import build_market_regimes
from quant_trading.research.runner import run_signal_research
from quant_trading.research.turnover import membership_turnover
from quant_trading.utils.config import CandidateSignalConfig, FeatureConfig, SignalResearchConfig


def cross_sectional_dataset(dates: int = 2, securities: int = 10) -> pd.DataFrame:
    index = pd.MultiIndex.from_product(
        [pd.bdate_range("2020-01-01", periods=dates), [f"S{i:02d}" for i in range(securities)]],
        names=["date", "ticker"],
    )
    signal = np.tile(np.arange(securities, dtype=float), dates)
    return pd.DataFrame({"signal": signal, "target_return_5d": signal}, index=index)


def test_perfect_positive_and_negative_daily_ic() -> None:
    data = cross_sectional_dataset(dates=1)
    positive = daily_information_coefficients(data, "signal", "target_return_5d", minimum_cross_section=5)
    assert positive["spearman_ic"].iloc[0] == pytest.approx(1.0)
    data["inverse"] = -data["signal"]
    negative = daily_information_coefficients(data, "inverse", "target_return_5d", minimum_cross_section=5)
    assert negative["spearman_ic"].iloc[0] == pytest.approx(-1.0)


def test_daily_ic_is_cross_sectionally_isolated() -> None:
    data = cross_sectional_dataset()
    first_date, second_date = data.index.get_level_values("date").unique()
    original = daily_information_coefficients(data, "signal", "target_return_5d", minimum_cross_section=5)
    data.loc[(second_date, slice(None)), "target_return_5d"] *= -1
    changed = daily_information_coefficients(data, "signal", "target_return_5d", minimum_cross_section=5)
    assert original.loc[first_date, "spearman_ic"] == changed.loc[first_date, "spearman_ic"]


def test_known_quantile_assignment_and_monotonic_returns() -> None:
    values = pd.Series(np.arange(1, 11, dtype=float), index=[f"S{i}" for i in range(10)])
    groups = assign_quantiles(values, 5)
    assert groups.tolist() == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    data = cross_sectional_dataset(dates=3, securities=10)
    returns = quantile_return_series(
        data, "signal", "target_return_5d", quantiles=5, minimum_cross_section=5
    )
    summary = summarize_quantiles(returns, expected_direction=1)
    assert summary.returns[1] < summary.returns[2] < summary.returns[5]
    assert summary.quantile_rank_correlation == pytest.approx(1.0)
    assert summary.adjacent_fraction_expected == pytest.approx(1.0)


def test_hac_inference_is_finite_for_deterministic_nonconstant_series() -> None:
    values = pd.Series(np.sin(np.arange(100)) * 0.05 + 0.02)
    result = infer_ic(values, hac_lags=4)
    assert np.isfinite(result.hac_standard_error)
    assert np.isfinite(result.hac_t_stat)
    assert 0 <= result.hac_p_value <= 1


def test_non_overlapping_offsets_select_expected_observations() -> None:
    values = pd.Series(np.arange(12, dtype=float), index=pd.bdate_range("2020-01-01", periods=12))
    result = non_overlapping_inference(values, horizon=5)
    assert result.loc[0, "valid_dates"] == 3
    assert result.loc[1, "valid_dates"] == 3
    assert result.loc[2, "valid_dates"] == 2
    assert result.index.tolist() == [0, 1, 2, 3, 4]


def test_multiple_testing_adjustments_match_known_values() -> None:
    adjusted = adjust_pvalues(pd.Series({"a": 0.01, "b": 0.04, "c": 0.20}))
    assert adjusted.loc["a", "bonferroni_p_value"] == pytest.approx(0.03)
    assert adjusted.loc["b", "bonferroni_p_value"] == pytest.approx(0.12)
    assert adjusted.loc["a", "fdr_q_value"] == pytest.approx(0.03)
    assert adjusted.loc["b", "fdr_q_value"] == pytest.approx(0.06)
    assert adjusted.loc["c", "fdr_q_value"] == pytest.approx(0.20)


def test_membership_turnover_exact() -> None:
    assert membership_turnover({"B", "C"}, {"A", "B"}) == pytest.approx(0.5)


def test_identical_and_inverted_signal_correlations() -> None:
    data = cross_sectional_dataset(dates=4)
    data["copy"] = data["signal"]
    data["inverse"] = -data["signal"]
    matrix = signal_correlation_matrix(
        data, ("signal", "copy", "inverse"), minimum_cross_section=5
    )
    assert matrix.loc["signal", "copy"] == pytest.approx(1.0)
    assert matrix.loc["signal", "inverse"] == pytest.approx(-1.0)
    pairs = highly_correlated_pairs(matrix, 0.8)
    assert len(pairs) == 3


def test_regime_labels_do_not_use_future_values() -> None:
    dates = pd.bdate_range("2020-01-01", periods=300)
    tickers = ["AAA", "SPY"]
    index = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    data = pd.DataFrame(index=index)
    data["price_to_sma_200"] = np.tile(np.linspace(-0.1, 0.1, 300), 2).reshape(300, 2).ravel()
    data["realized_vol_20"] = np.tile(np.linspace(0.1, 0.3, 300), 2).reshape(300, 2).ravel()
    original = build_market_regimes(data)
    cutoff = dates[249]
    changed = data.copy()
    future = changed.index.get_level_values("date") > cutoff
    changed.loc[future, ["price_to_sma_200", "realized_vol_20"]] *= -100
    recalculated = build_market_regimes(changed)
    pd.testing.assert_frame_equal(original.loc[:cutoff], recalculated.loc[:cutoff])


def test_block_bootstrap_is_reproducible() -> None:
    values = pd.Series(np.sin(np.arange(80)))
    first = block_bootstrap_mean_ci(values, iterations=200, block_length=8, seed=17)
    second = block_bootstrap_mean_ci(values, iterations=200, block_length=8, seed=17)
    assert first == second


def test_target_cannot_be_candidate_signal() -> None:
    data = cross_sectional_dataset(dates=1)
    with pytest.raises(ValueError, match="Target columns cannot"):
        daily_information_coefficients(
            data, "target_return_5d", "target_return_5d", minimum_cross_section=5
        )
    with pytest.raises(ValueError, match="Target columns cannot"):
        SignalResearchConfig(candidates=(CandidateSignalConfig(name="target_return_1d"),))


def test_calendar_audit_quantifies_missing_dates_and_longer_span() -> None:
    dates = pd.bdate_range("2020-01-01", periods=8)
    rows = [(date, ticker) for date in dates for ticker in ("AAA", "SPY")]
    index = pd.MultiIndex.from_tuples(rows, names=["date", "ticker"])
    panel = pd.DataFrame({"close": 100.0}, index=index).drop(index=(dates[2], "AAA"))
    audit = audit_panel_calendar(panel, horizon=5)
    assert audit.missing_ticker_dates == 1
    assert audit.five_row_targets_spanning_extra_sessions == 2
    assert audit.maximum_extra_sessions == 1
    assert audit.target_horizon_distribution == {5: 3, 6: 2}


def integrity_dataset(days: int = 80, securities: int = 30) -> pd.DataFrame:
    rng = np.random.default_rng(123)
    dates = pd.bdate_range("2018-01-01", periods=days)
    tickers = ["SPY"] + [f"S{i:02d}" for i in range(securities - 1)]
    index = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    latent = rng.normal(size=len(index))
    target = 0.02 * latent + rng.normal(scale=0.005, size=len(index))
    data = pd.DataFrame(index=index)
    data["signal_a"] = latent
    data["signal_b"] = rng.normal(size=len(index))
    data["signal_c"] = -latent
    data["signal_d"] = latent + rng.normal(scale=0.001, size=len(index))
    for horizon in (1, 5, 10, 20):
        data[f"target_return_{horizon}d"] = target
    data["avg_dollar_volume_20"] = rng.lognormal(15, 1, size=len(index))
    data["price_to_sma_200"] = np.tile(np.linspace(-0.05, 0.05, days), securities)
    data["realized_vol_20"] = np.tile(np.linspace(0.1, 0.3, days), securities)
    return data


def test_research_integrity_predictive_noise_inverse_and_copy() -> None:
    data = integrity_dataset()
    candidates = (
        CandidateSignalConfig(name="signal_a", expected_direction=1),
        CandidateSignalConfig(name="signal_b", expected_direction=0),
        CandidateSignalConfig(name="signal_c", expected_direction=-1),
        CandidateSignalConfig(name="signal_d", expected_direction=1),
    )
    config = SignalResearchConfig(
        candidates=candidates,
        minimum_cross_section=10,
        high_liquidity_fraction=0.7,
    )
    results = run_signal_research(data, FeatureConfig(), config)
    card = results.scorecard.set_index("signal")
    assert card.loc["signal_a", "mean_rank_ic"] > 0.8
    assert abs(card.loc["signal_b", "mean_rank_ic"]) < 0.05
    assert card.loc["signal_c", "mean_rank_ic"] < -0.8
    assert results.correlations.loc["signal_a", "signal_d"] > 0.99
    assert ((results.correlated_pairs["signal_a"] == "signal_a") & (results.correlated_pairs["signal_b"] == "signal_d")).any()
