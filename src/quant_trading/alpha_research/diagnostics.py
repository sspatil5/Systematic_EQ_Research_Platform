"""Cost, long-only, decile, orthogonality, and split signal diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_trading.research.ic import daily_information_coefficients, infer_ic
from quant_trading.research.quantiles import assign_quantiles, quantile_return_series, summarize_quantiles
from quant_trading.research.turnover import membership_turnover


def signal_summary(
    dataset: pd.DataFrame,
    signal: str,
    *,
    target: str = "target_return_5d",
    expected_direction: int = 1,
    minimum_cross_section: int = 20,
    quantiles: int = 5,
    hac_lags: int = 4,
) -> dict[str, object]:
    ic = daily_information_coefficients(
        dataset, signal, target, minimum_cross_section=minimum_cross_section
    )
    inference = infer_ic(ic["spearman_ic"], hac_lags=hac_lags)
    returns = quantile_return_series(
        dataset, signal, target, quantiles=quantiles,
        minimum_cross_section=minimum_cross_section,
    )
    quantile = summarize_quantiles(returns, expected_direction)
    return {
        "signal": signal, "valid_dates": inference.valid_dates,
        "mean_rank_ic": inference.mean, "hac_t_stat": inference.hac_t_stat,
        "p_value": inference.hac_p_value, "q_high_minus_low": quantile.q5_minus_q1,
        "monotonicity": quantile.quantile_rank_correlation,
        **{f"q{number}_return": value for number, value in quantile.returns.items()},
    }


def tail_reversal_diagnostics(
    dataset: pd.DataFrame,
    signal: str = "ret_1d",
    target: str = "target_return_5d",
    fractions: tuple[float, ...] = (0.05, 0.10, 0.20),
) -> pd.DataFrame:
    """Low-minus-high reversal spread and one-way membership turnover.

    Break-even cost is spread divided by total two-leg turnover. It is expressed in return units
    per dollar traded and is not an executable estimate.
    """
    rows = []
    for fraction in fractions:
        daily_spreads = []
        turnover = []
        previous_low: set[str] = set()
        previous_high: set[str] = set()
        for _, cross in dataset[[signal, target]].groupby(level="date", sort=True):
            valid = cross.dropna()
            count = max(1, int(np.ceil(len(valid) * fraction)))
            if len(valid) < max(10, 2 * count):
                continue
            ordered = valid.sort_values(signal)
            low = set(ordered.index.get_level_values("ticker")[:count])
            high = set(ordered.index.get_level_values("ticker")[-count:])
            daily_spreads.append(float(ordered.iloc[:count][target].mean() - ordered.iloc[-count:][target].mean()))
            if previous_low and previous_high:
                turnover.append(membership_turnover(low, previous_low) + membership_turnover(high, previous_high))
            previous_low, previous_high = low, high
        spread = float(np.mean(daily_spreads)) if daily_spreads else np.nan
        total_turnover = float(np.mean(turnover)) if turnover else np.nan
        rows.append({
            "tail_fraction": fraction, "oriented_low_minus_high_spread": spread,
            "two_leg_turnover": total_turnover,
            "break_even_one_way_cost": spread / total_turnover if total_turnover > 0 else np.nan,
            "break_even_one_way_bps": spread / total_turnover * 10_000 if total_turnover > 0 else np.nan,
        })
    return pd.DataFrame(rows)


def long_only_diagnostics(
    dataset: pd.DataFrame,
    signal: str,
    *,
    target: str = "target_return_5d",
    benchmark: str = "SPY",
    expected_direction: int = 1,
    quantiles: int = 5,
) -> dict[str, float | str]:
    rows = []
    for date, cross in dataset[[signal, target]].groupby(level="date", sort=True):
        valid = cross.dropna()
        if len(valid) < 20:
            continue
        groups = assign_quantiles(valid[signal], quantiles)
        desired = quantiles if expected_direction > 0 else 1
        opposite = 1 if desired == quantiles else quantiles
        selected = valid.loc[groups == desired, target]
        rejected = valid.loc[groups == opposite, target]
        if selected.empty or rejected.empty:
            continue
        spy = (
            float(cross.xs(benchmark, level="ticker")[target].iloc[0])
            if benchmark in cross.index.get_level_values("ticker") else np.nan
        )
        rows.append({
            "selected": selected.mean(), "opposite": rejected.mean(),
            "universe": valid[target].mean(), "spy": spy,
        })
    frame = pd.DataFrame(rows)
    return {
        "signal": signal,
        "selected_absolute_return": float(frame["selected"].mean()),
        "selected_minus_universe": float((frame["selected"] - frame["universe"]).mean()),
        "selected_minus_spy": float((frame["selected"] - frame["spy"]).mean()),
        "opposite_minus_universe": float((frame["opposite"] - frame["universe"]).mean()),
    }


def orthogonality_table(dataset: pd.DataFrame, signals: tuple[str, ...]) -> pd.DataFrame:
    exposures = {
        "momentum": "momentum_12_1", "volatility": "realized_vol_20",
        "beta": "beta_20", "liquidity": "avg_dollar_volume_20",
    }
    required = tuple(dict.fromkeys((*signals, *exposures.values())))
    ranked = dataset[list(required)].groupby(level="date").rank(method="average", pct=True)
    rows = []
    for signal in signals:
        row: dict[str, object] = {"signal": signal}
        for label, exposure in exposures.items():
            if signal == exposure:
                row[f"correlation_{label}"] = 1.0
                continue
            pair = ranked[[signal, exposure]].dropna()
            work = pd.DataFrame({
                "a": pair[signal], "b": pair[exposure],
                "ab": pair[signal] * pair[exposure],
                "a2": pair[signal].pow(2), "b2": pair[exposure].pow(2),
            })
            grouped = work.groupby(level="date")
            means = grouped.mean()
            counts = grouped.size()
            covariance = means["ab"] - means["a"] * means["b"]
            denominator = np.sqrt(
                (means["a2"] - means["a"].pow(2))
                * (means["b2"] - means["b"].pow(2))
            )
            daily = (covariance / denominator).where(counts >= 20)
            row[f"correlation_{label}"] = float(daily.mean())
        rows.append(row)
    return pd.DataFrame(rows)
