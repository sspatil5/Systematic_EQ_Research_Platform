"""Short-sample-safe prospective operational report."""

from pathlib import Path
import json
import pandas as pd

from quant_trading.prospective.operations import initialize, write_status


OUTPUT_SCHEMAS = {
    "prospective_performance.csv":["date","account","gross_equity","net_equity","gross_return","net_return","drawdown"],
    "prospective_ic.csv":["signal_date","outcome_date","signal","spearman_ic","q5_minus_q1","top10_minus_universe"],
    "universe_history.csv":["signal_date","eligible_count","added_count","removed_count","missing_pct"],
    "turnover.csv":["date","account","gross_traded_notional","pretrade_equity","gross_turnover"],
    "exposures.csv":["date","account","sector","weight","largest_position","top5_concentration","cash_pct"],
    "drift.csv":["signal_date","metric","value","warning"],
}


def write_operational_report(config_path="config/prospective.yaml"):
    config, store = initialize(config_path); status = write_status(config_path)
    config.report_root.mkdir(parents=True, exist_ok=True)
    for filename, columns in OUTPUT_SCHEMAS.items():
        path = config.report_root / filename
        if not path.exists(): pd.DataFrame(columns=columns).to_csv(path, index=False)
    report = f"""# Phase 5 prospective status

Experiment: `{config.experiment_id}`

Operational status: **DATA SOURCE INSUFFICIENT FOR PROSPECTIVE COLLECTION**

No prospective signal event, order, execution, holding, return, or performance claim exists. The
experiment architecture is ready, but the frozen universe requires a broad contemporaneous U.S.
common-equity security master with stable IDs, exchange/type, and point-in-time sector. No such
provider is configured; the system fails closed instead of reverting to the historical 81 names.

- Age/weekly observations/trades/completed outcomes/IC observations: 0
- Shadow equity: not initialized by an observation
- Manifested prospective artifacts: {len(pd.read_csv(store.manifest))}
- Brokerage connection: absent by design
- Sample reliability: NO SAMPLE
- Next action: configure and validate an eligible security-master/market-data provider, then wait for
  the next scheduled last-session-of-week close. Do not backfill.

## Frozen operating design

- Universe: contemporaneously enumerated NYSE/Nasdaq/NYSE American common stocks with sector,
  price >= $5, 252 sessions, and lagged 20-session dollar volume >= $20 million.
- Signals: exact Phase 3.5 sector-neutral 12-1 momentum and exact fixed 50/50 challenger.
- Portfolios: independent $30,000 Top-10 equal-weight persistent shadow accounts, whole shares,
  long-only, no leverage; raw momentum uses identical mechanics.
- Timing: after-close Stage A creates price-free frozen orders; subsequent Stage B consumes their
  hash and observes the next valid open without recomputing signals.
- Costs: 5 bps one way, charged once to cash; identical realized trade quantities are repriced at
  0/2/5/10/20 bps for diagnostics.
- Missing opens: skip and record. Failed collection without a pre-future-data raw snapshot is
  `MISSED`, never reconstructed. Existing dates are idempotent and revisions require a new artifact
  or experiment version.
- Integrity: immutable Parquet/JSON artifacts, SHA-256 manifest, row/date metadata, and append-only
  transition log. `prospective-verify` and `prospective-audit` validate the experiment.
- Benchmarks: prospective total-return-consistent SPY, contemporaneous equal weight, and raw 12-1
  Top 10, aligned to identical observation periods.
- Review gates: 3 months operations only, 6 months preliminary, 12 months first meaningful review;
  no automatic live authorization. Advancement additionally requires intact operations, positive
  signal persistence/net equal-weight excess, cost robustness, and acceptable concentration.

## Implementation and limitations

The Phase 5 package contains no brokerage integration or order-submission capability. Twenty-one
deterministic prospective tests cover immutability, hashes, timing, two-stage separation, sizing,
persistence, leverage, costs, universe/sector history, outcomes, idempotency, audit entries,
versioning, missing opens, benchmark alignment, and absence of brokerage code.

The unresolved blocker is data enumeration: yfinance can download named symbols but cannot provide
the required broad contemporaneous security master with stable IDs, security type, exchange, and
point-in-time sector. The current static 81-name research universe is expressly prohibited as a
fallback. No performance chart or statistic is generated with zero observations.

The first legitimate observation was **not captured**.

D. DATA SOURCE INSUFFICIENT FOR PROSPECTIVE COLLECTION
"""
    (config.report_root / "latest_prospective_report.md").write_text(report, encoding="utf-8")
    store.audit("REPORT_GENERATED", "", "prospective-report", "SUCCESS",
                (config.report_root / "latest_prospective_report.md",))
    return status
