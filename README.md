# Quantitative Trading Research Platform

The local **AXIOM quantitative research dashboard** adds six artifact-backed research screens,
a FastAPI integration, and isolated background run controls. See [dashboard setup and architecture](docs/dashboard.md)
for the complete implementation, source inventory, filter semantics, validation, and limitations.

```bash
source .venv/bin/activate
python -m pip install -e ".[dashboard,research,dev]"
cd dashboard
npm ci
cd ..
python scripts/dashboard.py
```

Open http://127.0.0.1:5173. Existing research results load without rerunning experiments.

A leakage-aware Python research platform for cross-sectional U.S. equity ranking. The goal is
credible systematic research and paper/shadow trading—not an impressive-looking in-sample
backtest. Live order submission is intentionally out of scope.

## Current status: Phase 3.5

Phase 1 provides the package foundation and daily market-data pipeline:

- a configurable, explicit universe of 80 liquid U.S. equities and ETFs;
- adjusted daily OHLCV acquisition through `yfinance`;
- request-specific local Parquet caching;
- validation of duplicate dates, incomplete rows, non-finite/negative data, impossible OHLC bars,
  negative volume, and unusually large adjusted returns;
- canonical panel output indexed by `(date, ticker)`;
- typed, strict YAML configuration and deterministic synthetic tests.

Phase 2 transforms that immutable canonical panel into a research dataset:

- adjusted-close momentum, mean-reversion, realized volatility, volume/liquidity, and SPY-relative
  features;
- configurable daily cross-sectional ranks and z-scores;
- independently constructed 1/5/10/20-session forward-return targets;
- optional future-return rank and SPY-excess targets;
- queryable feature metadata, structural validation, and a missingness-aware dataset summary.

Phase 3 evaluates a deliberately configured subset of economically distinct raw signals. It does
not treat target columns, the raw market benchmark, cross-sectional transformations, or every
near-duplicate parameterization as independent discoveries. Diagnostics include daily Pearson and
Spearman IC, Newey-West inference, all non-overlapping offsets, forward-return research quantiles,
signal decay, temporal and regime stability, turnover, liquidity conditioning, redundancy flags,
multiple-testing corrections, and optional moving-block bootstrap intervals.

Phase 3.5 is explicitly post-selection research. It freezes 2010–2021 as development and 2022 onward
as confirmation, registers hypotheses before evaluation, and investigates sector/beta controls,
Fama–MacBeth coefficients, predefined momentum variants, idiosyncratic volatility, reversal costs,
overnight/intraday decomposition, and fixed-weight signal combinations. Current sector labels are
cached research controls and are not represented as historical point-in-time classifications.

The package uses `src/quant_trading` instead of a top-level package named `src`. This prevents
ambiguous imports such as `data.loader` and makes editable/installable packaging reliable.

## Installation

Python 3.12 or newer is required.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
pytest
```

Build the development-universe panel:

```bash
quant-research download-data --config config/research.yaml
```

Then build the Phase 2 dataset without overwriting the canonical panel:

```bash
quant-research build-features --config config/research.yaml
```

Run the reproducible Phase 3 analysis:

```bash
quant-research analyze-signals --config config/research.yaml
```

Run the frozen Phase 3.5 development/confirmation analysis:

```bash
quant-research expand-alpha-research --config config/research.yaml
```

Machine-readable tables, twelve diagnostic figures, and the cautious Markdown research report are
written under `reports/phase3/`. Quantile series are explicitly forward-return research portfolios;
they are not executable strategy returns.

Raw downloads are cached under `data/cache/`; the cleaned panel is written to
`data/processed/daily_panel.parquet`. Features and targets are written separately to
`data/processed/features.parquet`. Generated data and reports are ignored by Git.

## Information timing convention

Daily OHLCV for session `t` is considered available only after that session's close. A feature
labeled `t` may use the close and volume from `t` plus earlier observations, but never data from
`t+1` or later. Such a signal can execute no earlier than `t+1`; execution itself is intentionally
not implemented in Phase 2.

Trailing returns are `close[t] / close[t-L] - 1`. Moving-average distances are
`close[t] / SMA_L[t] - 1`. `momentum_12_1` is `close[t-21] / close[t-252] - 1`, an approximate
12-month return excluding the latest 21 sessions. Volatility is the trailing sample standard
deviation of daily returns annualized by `sqrt(252)`. The date-`t` residual return uses the 20-day
beta estimated through `t-1`, while reported `beta_20[t]` itself uses returns through `t`.

The raw target is deliberately forward-looking and never eligible as a feature:
`target_return_Ld[t] = close[t+L] / close[t] - 1`. It describes future close-to-close movement;
it is not a claim about the return achievable by the later open-execution convention.

## Missing-data policy

The feature layer never applies blanket zero imputation. Insufficient price history, missing source
bars, zero denominators, constant cross-sections, and unavailable future target endpoints remain
`NaN`. Cross-sectional transforms use only the non-missing securities present on the same date and
require at least two observations. Later model code—not this layer—will decide which rows qualify
for fitting.

## Quantitative assumptions and controls

- `auto_adjust=True` is mandatory in this first loader. OHLC prices are adjusted consistently by
  the provider; raw corporate actions are not currently retained.
- The end date passed to yfinance is exclusive. A null end date means the latest available data;
  its cache is deliberately persistent until `refresh: true` is set.
- Extreme adjusted close-to-close moves are flagged for review, not deleted. Automatically
  removing them would risk deleting genuine market events.
- Missing rows cannot be reliably distinguished from exchange holidays without a trading-calendar
  dependency. Per-ticker shifts count that ticker's observations, so a missing individual session
  makes an `h`-row horizon differ from exactly `h` exchange sessions. This is retained as an
  explicit limitation pending calendar-aware reindexing.
- Dollar volume is adjusted close multiplied by provider-reported share volume. It is a useful
  liquidity proxy, but adjustments and historical volume conventions mean it is not perfect
  executable notional liquidity.
- The development universe is selected using present-day liquidity. Historical results therefore
  have survivorship and selection bias and must never be described as a point-in-time S&P 500 test.
- No model, portfolio, backtest, broker, or live execution implementation is claimed in this phase.

## Planned architecture

Subsequent phases will add signal diagnostics, models and walk-forward selection,
portfolio/execution simulation, risk/analytics, experiment tracking, and a
paper broker. The future `SchwabBroker` will remain a refusing stub until a separate, explicit live
trading project decision and additional safeguards are made. Credentials will only come from the
environment; `.env` and generated artifacts are excluded from version control.

## Research workflow

Each phase follows the same gate: state assumptions, implement a narrow component, test it with
known synthetic data, run the full suite, document limitations, and only then proceed. Untouched
walk-forward test folds will be treated as final evaluation data; they will not be recycled for
hyperparameter or strategy decisions.

## Next phase

Phase 4 should introduce transparent baselines and chronological walk-forward splitting only after
real Phase 3 results have been reviewed. If the calendar audit finds material unequal-session
horizons, a Phase 2.1 calendar remediation should occur before interpreting signal evidence or
starting model construction.

## Disclaimer

This is research software, not investment advice. The risk limits in configuration are conservative
illustrative placeholders for a roughly $30,000 paper account and are not personalized recommendations.
