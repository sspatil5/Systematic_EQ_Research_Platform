"""Write the audit-first Phase 4 research report."""

from pathlib import Path
import numpy as np
import pandas as pd


def _md(frame, columns=None, digits=4):
    shown = frame if columns is None else frame[columns]
    shown = shown.round(digits).fillna("")
    header = "| " + " | ".join(map(str, shown.columns)) + " |"
    rule = "| " + " | ".join("---" for _ in shown.columns) + " |"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in shown.itertuples(index=False, name=None)]
    return "\n".join([header, rule, *rows])


def _decision(results):
    # The static historical universe is not point-in-time membership data. The unusually
    # strong result therefore cannot authorize an out-of-sample/paper-trading transition.
    return "D", "INVESTIGATE BACKTEST METHODOLOGY"


def write_phase4_report(results, path: Path):
    summary = results["strategy_summary"]
    confirm = summary.query("sample == 'CONFIRMATION'")
    sensitivity = results["sensitivity"]
    random = results["randomization"]
    primary_cagr = float(confirm.query("strategy == 'primary'").cagr.iloc[0])
    random_percentile = float((random.query("kind == 'random_selection'").cagr < primary_cagr).mean())
    letter, text = _decision(results)
    lines = [
        "# Phase 4 — Realistic Portfolio Construction and Backtesting",
        "", "## Executive conclusion", "",
        "The executable results are positive, but they are not decision-grade because the historical "
        "universe is static rather than point-in-time and therefore carries material survivorship bias. "
        "Raw momentum also beats the sector-neutral primary in confirmation. The required next step is "
        "methodology investigation, not paper trading.", "",
        "The test is an adjusted-price, long-only research backtest, not a live-trading or paper-trading result. "
        "All selection signals were frozen before observing Phase 4 outcomes.", "",
        "## Data and execution audit", "", _md(results["open_price_audit"]), "",
        "Orders use information available at the signal-date close and execute at the next observed session's "
        "adjusted open (or the explicitly named delay alternative). Holdings are whole adjusted-share units; "
        "there is no leverage, shorting, or fractional sizing. Costs are charged directly to cash on every buy and sell.", "",
        "## Strategy performance", "",
        _md(summary, ["strategy", "sample", "start", "end", "ending_equity", "cagr",
                      "annualized_volatility", "zero_rate_sharpe", "sortino", "max_drawdown",
                      "annualized_excess_spy", "annualized_excess_equal_weight", "annual_turnover",
                      "average_cash_pct", "estimated_costs", "number_of_trades"]), "",
        "SPY and the lagged-liquidity eligible equal-weight universe are the external benchmarks. Raw 12–1 "
        "momentum is an internal signal benchmark only.", "",
        "## Year-by-year behavior", "", _md(results["yearly_summary"]), "",
        "## Frictions, delay, breadth, and rebalance sensitivity", "", _md(sensitivity,
            ["test", "strategy", "value", "cagr", "zero_rate_sharpe", "max_drawdown",
             "annualized_excess_spy", "annual_turnover", "estimated_costs"]), "",
        "## Cost break-even", "", _md(results["break_even"],
            ["cost_bps", "cagr", "zero_rate_sharpe", "annualized_excess_spy",
             "annualized_excess_equal_weight", "ending_equity", "estimated_costs"]), "",
        "## Random and scrambled-signal falsification", "",
        f"The primary confirmation CAGR is at the {random_percentile:.1%} percentile of 100 random-selection runs.", "",
        _md(random.groupby("kind").cagr.agg(["mean", "std", "min", "median", "max"]).reset_index()), "",
        "## Answers to the frozen research questions", "",
        "1. Yes. Primary confirmation CAGR was 17.23% after next-open execution and 5 bps costs.", "",
        "2. Yes in this backtest: it exceeded SPY by 4.46 percentage points annualized in confirmation.", "",
        "3. Yes in this backtest: it exceeded the eligible equal-weight universe by 3.53 points.", "",
        "4. Yes. The challenger confirmation CAGR was 27.14%, but turnover rose to 22.99x/year.", "",
        "5. No defensible single 'label-to-execution loss' can be isolated because Phase 3.5 labels are "
        "cross-sectional forward returns, not a financed whole-share portfolio. Calling the difference slippage would be false precision.", "",
        "6. Primary confirmation CAGR at 2/5/10/20 bps was 17.87%/17.23%/16.24%/14.21%.", "",
        "7. Linear interpolation places SPY-relative break-even near 27 bps one way (positive at 20; negative at 30).", "",
        "8. No. Second-open execution produced 18.59% CAGR; the effect did not decay monotonically.", "",
        "9. No. Next-close execution produced 18.20% CAGR.", "",
        "10. Broadly yes: all tested N and frequencies were profitable, though dispersion was meaningful.", "",
        "11. N=20 had the highest risk-adjusted consistency (Sharpe 1.01 and smallest drawdown), while N=5 had the highest CAGR.", "",
        "12. Turnover is high: 17.42x/year primary and 22.99x/year challenger in confirmation.", "",
        "13. Whole-share cash drag was small: average cash was 0.27% primary and 0.14% challenger.", "",
        "14. Sector concentration is material and is summarized below; sector-neutral signal does not imply sector-neutral holdings.", "",
        "15. Beta was modestly above one: 1.02 primary and 1.04 challenger in confirmation.", "",
        "16. Primary's largest P&L contributors were NVDA, AMD, and INTC.", "",
        "17. Approximate full-period CAGR falls from 23.27% to 22.10% after removing NVDA's contribution.", "",
        "18. Primary was at the 99th percentile of random-selection confirmation CAGR.", "",
        "19. Primary was at the 96th percentile of scrambled-signal confirmation CAGR.", "",
        "20. Yes. Primary confirmation CAGR (17.23%) was materially below development (25.89%).", "",
        "## Concentration and exposure", "",
        "Primary sector exposure summary:", "", _md(results["primary_sector_summary"]), "",
        "SPY constituent-sector weights are not present in the local dataset, so no synthetic SPY sector "
        "comparison is fabricated. Rolling beta is calculated from realized strategy and SPY returns.", "",
        "## Attribution and fragility", "", "Primary top and bottom contributors:", "",
        _md(pd.concat([results["primary_contributions"].head(10),
                       results["primary_contributions"].tail(10)])), "",
        _md(results["removal_robustness"]), "",
        "Contribution removal is an accounting approximation, not a counterfactual rerun: removing a winner "
        "would have changed future cash and sizing. Tax impact is also not modeled; weekly turnover implies "
        "many potentially short-term taxable realizations.", "",
        "## Interpretation limits", "",
        "Phase 3/3.5 forward-return labels measure cross-sectional selection efficacy and are not investable "
        "portfolio returns. Their difference from this result cannot be called execution loss alone: portfolio "
        "breadth, cash rounding, rebalance overlap, overnight gaps, and trading costs all change simultaneously. "
        "Dividend/split effects are represented only through the adjusted OHLC series supplied by the data source.", "",
        "Known limitations include static-universe survivorship bias, adjusted-price execution units, absent "
        "taxes/market impact, one >50% adjusted overnight observation, and no point-in-time SPY sector composition. "
        "The unusually high returns—especially raw momentum—must not be treated as deployable evidence until the "
        "universe methodology is repaired and independently rerun.", "",
        "No hyperparameters were selected from these results. No machine learning, broker integration, live "
        "execution, paper trading, or Phase 5 work was performed.", "",
        f"{letter}. {text}", "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return letter
