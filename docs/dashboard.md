# Quantitative Research Dashboard

A local React/TypeScript dashboard and thin FastAPI integration around the existing
`quant_trading` package. Research calculations and historical files remain unchanged.
The interface is branded **AXIOM**, a presentation name for this repository's research workspace.

## Quick start

Requires Python 3.12+, Node 22.12+ (Node 22.18 tested), and npm. From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dashboard,research,dev]"
cd dashboard
npm ci
cd ..
python scripts/dashboard.py
```

Open **http://127.0.0.1:5173**. API documentation is at
**http://127.0.0.1:8000/docs**. Ctrl-C stops both servers and the owned research worker.
Python changes require a restart; React and CSS changes update through Vite.
No research stage runs on startup, navigation, or filter changes.

To start the two layers separately:

```bash
# Terminal 1, repository root, virtual environment activated
python -m uvicorn quant_dashboard.app:app --host 127.0.0.1 --port 8000

# Terminal 2
cd dashboard
npm run dev
```

For a built frontend served by the API on one local port:

```bash
cd dashboard
npm run build
cd ..
python -m uvicorn quant_dashboard.app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 after the build. Restart the API after the first build so it
mounts `dashboard/dist`. `npm run preview` alone does not proxy the API; use the API
server for the integrated production build.

`QUANT_RESEARCH_ROOT` optionally selects another repository root with the same layout.
It is an operator environment variable, never a browser-supplied path. No other environment
variables, brokerage credentials, cloud accounts, or hosted services are required. Do not expose
the local API to the internet: this MVP has no multi-user authentication.

## Repository inspection and implementation plan

Inspection found a Python package with strict Pydantic/YAML configurations, an argparse CLI,
file-based research outputs, and deterministic pytest tests. There was no API, frontend,
database-backed experiment tracker, or task queue. The existing README describes an earlier
phase than the actual code and local outputs.

The implemented sequence was:

1. Inventory canonical data, statistical outputs, frozen definitions, importer failures, and CLI stages.
2. Add read-only artifact adapters and typed FastAPI routes without changing the engine.
3. Build a shared research context and six MVP screens using actual stored outputs.
4. Add a single background worker, SQLite metadata, immutable configuration/input snapshots,
   and separate output directories for new runs.
5. Verify source agreement, missing-data behavior, file access, jobs, filters, and browser rendering.

| Existing capability | Verified source | Dashboard integration |
| --- | --- | --- |
| Adjusted OHLCV and validation | `data/loader.py`, `data/cleaner.py`, `data/processed/daily_panel.parquet` | Dataset dates, freshness, counts, coverage, and per-ticker missingness |
| Explicit development universe | `data/universe.py` | 81 observed symbols, labelled static and survivorship-biased |
| Current sector controls | `alpha_research/sectors.py`, saved `sector_mapping.csv` | Sector filters with explicit non-point-in-time limitation |
| Bloomberg import and fail-closed schema checks | `prospective/bloomberg.py`, Phase 5 import Markdown, source XLSX, manifest and audit CSVs | Existing failure diagnostics, mapping counts, conflicts, history, hash verification; isolated re-import action |
| Feature definitions and calculations | `features/metadata.py`, `features/pipeline.py`, configured momentum/reversal/volatility/volume/market features | Actual signal descriptions/lookbacks; feature generation action; full explorer deferred |
| IC, HAC inference, FDR, liquidity, quantiles, decay, correlation | `research/runner.py`, `research/ic.py`, `research/multiple_testing.py`, `reports/phase3/*` | Signal scorecard and existing diagnostic series |
| Development and confirmation research | `alpha_research/runner.py`, `alpha_research/split.py`, `reports/phase3_5/*` | Stored sample-specific IC, inference, and quantile results; no invented validation labels |
| Portfolio, execution, costs, sizing | `backtest/engine.py`, `backtest/execution.py`, `backtest/costs.py`, `portfolio/*`, frozen Phase 4 definition | Configuration reference, exact historical freeze, existing backtest launch |
| Performance, sample summaries, risk | `analysis/performance.py`, `risk/metrics.py`, `reports/phase4/*` | Stored metrics, benchmarks, equity, drawdown, rolling diagnostics, monthly/annual returns |
| Holdings, trades, sector exposures, sensitivity/randomization | Phase 4 Parquet and CSV artifacts | Preview/export through Reports; dedicated risk/robustness screens deferred |
| Prospective storage and integrity | `prospective/storage.py`, `reports/phase5/operational_status.json` | Separate unavailable prospective module; no simulated activity shown as live trades |

Observed market data covers 2010-01-04 through 2026-08-14 and contains 336,391 rows in
the inspected checkout. These are inspection facts, not UI constants: the API computes metadata
from the current files. The Bloomberg snapshot failed because two files lack `Primary Exchange MIC`;
the API reads that actual report and never treats its diagnostics as an authorized universe.

New backend functionality comprises artifact indexing and safe downloads, derived display series,
run metadata, input/output hashes, job exclusion, process orchestration, and local API contracts.
No signal, statistical test, portfolio rule, cost function, or execution model was rewritten.

## Architecture and files

```text
dashboard/
  src/App.tsx                  navigation and shared run/strategy/sample/date context
  src/pages/                  six MVP views
  src/components/             reusable tables, charts, states, metric cards
  src/components/ui/          shadcn-style Button/Card primitives; Radix Slot and CVA
  src/types.ts                frontend API contracts
  src/lib.ts                  cancellable requests, polling, formatters, CSV export
  e2e/                        Playwright browser checks
src/quant_dashboard/
  app.py                      FastAPI routes, structured request logging, static serving
  schemas.py                  Pydantic response and action schemas
  repository.py               read-only artifact/data adapters, filtering, serialization
  jobs.py                     SQLite store, single-worker queue and process manager
  worker.py                   fixed mapping to existing Python CLI functions
scripts/dashboard.py          paired local development startup and shutdown
tests/test_dashboard.py        API, integrity, serialization and job integration tests
data/dashboard/               ignored runtime state
  runs.sqlite3
  runs/<UUID>/
    config.yaml               immutable effective configuration
    request.json              validated action parameters
    input_manifest.json       dataset identifiers, sizes and SHA-256 digests
    execution.log
    checksums.json            completed config/input/output digests
    outputs/                  phase-specific research artifacts
```

The frontend uses React, TypeScript, Vite, Tailwind v4, small shadcn-style components,
Recharts, TanStack Table, and Lucide icons. No remote fonts or image services are needed.
Chart/table vendors are split into separate build chunks. The API uses ordinary pandas/Parquet
reads with a bounded cache invalidated by file size and nanosecond modification time.

## Available screens

- **Overview:** dataset status, freshness, coverage, selected backtest metrics and benchmarks,
  equity curve, research activity, signal snapshot, and data-quality warnings.
- **Data & universe:** server-side ticker/sector/liquidity filters, sorting and pagination,
  observed coverage, dollar volume, and the actual Bloomberg schema/mapping/conflict diagnostics.
- **Signal research:** complete-sample scorecards, development/confirmation evidence, stored
  daily rank IC, forecast decay, quantile means, t-statistic comparison, and correlation heatmap.
- **Backtest results:** exact stored summaries, three equity curves, underwater drawdown,
  126-session rolling Sharpe/volatility/beta, monthly heatmap, annual comparison, configuration
  provenance, and the frozen historical methodology.
- **Reports & audit:** server-filtered/sorted/paginated artifact index, safe previews and original
  downloads, text/config views, PNG figures, and recorded-hash verification.
- **Runs & configuration:** prerequisites, fixed stage controls, queued/running/succeeded/failed
  status, polled logs, original error tracebacks, input versions, snapshots, and output locations.

Planned modules are visibly marked: Feature Explorer, Alpha Validation, Portfolio & Risk,
Robustness Analysis, and Prospective Monitor. Their placeholders never generate data.

## Research context and metric semantics

**Repository artifacts** is a collection of original files, not a fabricated single historical run.
Original execution timestamps, code revisions, and machine-readable config snapshots were not
recorded for these files. The UI labels that absence and distinguishes file modification times
from experiment timestamps. New dashboard runs have explicit IDs, timestamps, and snapshots.

The full/development/confirmation backtest summaries are read directly from `strategy_summary.csv`.
Numeric values preserve full Python float precision; non-finite values serialize as `null`.
All nine saved strategy/sample combinations were checked against their source rows (270 values).
Custom date ranges call the existing `performance_metrics` function on stored daily returns.
No backtest or signal experiment reruns for a filter change.

Each equity comparison compounds saved daily net/benchmark returns and normalizes the selected
sample to its original initial capital, inferred from the saved summary. This matches the existing
`sample_summaries` convention. It does not reset or rerun the historical portfolio. Drawdown
uses the existing helper over the selected recorded equity series. Rolling diagnostics require
126 observations in the selected window. Monthly/annual returns compound saved daily returns.

The historical configuration panel labels current YAML as a **reference**, not an original run
snapshot. The accompanying `research_freeze.md` displays the actual stored methodology. A new
run's configuration panel uses its own stored snapshot.

Signal inference remains the stored complete-sample statistic. Date filters affect available daily
IC and quantile series, not the scorecard's p/q-values or evidence classification. Decay and
correlation are full Phase 3 summaries and are hidden for split periods. For expanded signals
without daily IC or quantile series, the API shows available stored sample-level quantile means
and leaves the daily/decay views empty. Development/confirmation IC fields remain unavailable
when the signal was not included in that research design. A significant statistic is never
automatically called validated alpha or an economically profitable strategy.

Universe coverage uses observed ticker-sessions divided by the selected panel-calendar sessions;
missingness includes pre-listing dates. It is not an exchange-calendar completeness guarantee.
Liquidity eligibility means the last available stored 20-session dollar volume exceeds the
configured backtest floor. It is not security-master approval. Authoritative exchange/permanent
identifier fields remain absent until a valid security master exists.

Reports retain their original contents regardless of sample/strategy/date selection. Run selection
changes the browsed artifact set. Unknown runs and files return explicit errors; missing outputs
produce empty states. Data freshness is computed using America/New_York calendar dates.

## Pipeline execution and reproducibility

The allowlist exposes `build-features`, `analyze-signals`, `expand-alpha-research`,
`run-realistic-backtest`, and file-based `bloomberg-import`. All call existing Python functions.
The full realistic backtest includes the existing 100-seed robustness design and may take hours.
Its parameters are not reduced to make a UI run faster. Launch actions use the repository's
current YAML and canonical inputs; they do not automatically chain outputs from earlier dashboard
jobs. Browse those outputs through their run context. An explicit upstream-run selector can be
added later without changing the research engine.

A SQLite unique partial index prevents any two active stages from conflicting, including across
API instances sharing the store. Requests cannot supply shell commands, config paths, output
paths, arbitrary inputs, or tuning parameters. Bloomberg imports accept only an ISO source date
and always use the fixed repository XLSX directory. Failed imports remain failed and keep their
diagnostic artifacts. No upload endpoint or validation bypass exists.

Each run gets a UUID and a fresh directory. Effective output, cache, and prospective import roots
are redirected there. Original reports and canonical inputs are not overwritten. Configurations,
dataset hashes, and Git HEAD are captured before execution; workers reject changed inputs.
Completed output hashes are written before the final run status. A rerun creates a new version
instead of modifying a prior run. This is independent local metadata, not a claim of institutional
preregistration. Git HEAD does not capture uncommitted source edits; the current dirty worktree
is not archived as a full code snapshot.

The process manager is a small queue boundary that can be replaced with a dedicated task worker.
Use a single local Uvicorn worker. Shutdown terminates owned subprocesses and records failure;
startup marks runs owned by a dead API process as failed. Jobs are not automatically resumed.
Cancellation is not exposed; therefore no misleading canceled status is advertised.

## API

All paths are under `/api`; interactive schemas are at `/docs` on the API server.

| Method / path | Purpose |
| --- | --- |
| `GET /health`, `/context` | Local environment status and selectable contexts |
| `GET /overview`, `/dataset`, `/universe` | Status, dataset metadata, paginated coverage |
| `GET /signals` | Stored scorecards and supported diagnostics |
| `GET /backtest` | Metrics, benchmark comparisons, equity, drawdown, rolling/monthly/annual series |
| `GET /bloomberg` | Original importer status and audit events |
| `GET /artifacts` | Safe, paginated artifact catalog |
| `GET /artifacts/{id}/preview`, `/download`, `/image`, `/integrity` | Content and hash operations |
| `GET /stages`, `/runs`, `/config` | Prerequisites, history and reference/snapshot configuration |
| `POST /runs` | Validated allowlisted action; returns 202 and run metadata |
| `GET /runs/{id}`, `/runs/{id}/logs` | Polled worker status and bounded log tail |

Read filters include `run_id`, `strategy`, `period`, `start`, and `end` where relevant.
Universe/artifact tables have server-side search/filtering, bounded page sizes and sorting.
Unrecognized sort columns, reversed dates, unknown runs, missing prerequisites, and active-job
conflicts produce errors. Error payloads use `error` and `detail`. Artifact IDs are opaque hashes
of approved relative locations; downloads resolve against a server-owned index, revalidate allowed
roots, and reject escaping symlinks. HTML/SVG are not rendered as active inline documents.
CSV exports protect spreadsheet formula cells. Mutation origins are restricted to the local UI;
the browser uses a same-origin Vite proxy or the built frontend served by FastAPI.

## Validation

With the dashboard and research extras installed:

```bash
pytest
cd dashboard
npm test
npm run build
```

Browser integration checks use the real local artifacts and require both servers:

```bash
cd dashboard
npm run test:e2e
```

Playwright is configured for installed Google Chrome. On a machine without Chrome, install it
or update `playwright.config.ts` to use Playwright Chromium after `npx playwright install chromium`.
Browser screenshots and traces are written to ignored `dashboard/test-results`.
Synthetic API/frontend test fixtures exist only in temporary test directories and test files;
there is no production mock-data fallback. API tests are skipped when the optional FastAPI/httpx
dependencies are not installed, preserving the original package's lightweight test installation.

Tests cover source-value fidelity, full float precision/nulls, custom dates, missing data,
server filters/pagination, path and symlink rejection, hash matches/mismatches, action validation,
duplicate jobs, successful isolated worker execution, input-change failures and persisted metadata.
Frontend checks cover rendering, table filtering/sorting/pagination, missing metrics, retry states,
and stale-response protection. Browser checks cover source agreement, shared sample/dates, import
failures, charts/screens, report integrity, run prerequisites, and mobile navigation.

## Extending the dashboard

1. Implement a research signal in `quant_trading` using its existing validation and metadata rules.
2. Produce an explicit, reproducible output through the existing research pipeline.
3. Add a read-only adapter in `repository.py` and a response schema in `schemas.py`.
4. Add its TypeScript contract and an evidence-supported visualization; expose an empty state if
   the output was not generated. Do not reconstruct significance statistics from a display chart.
5. For an action, extend the fixed stage schema and worker mapping with isolated output paths and
   prerequisite validation; add an integration test before enabling its button.

## Remaining limitations

- Existing data is stale and survivorship-biased; it is not a repaired point-in-time universe.
  Adjusted prices, static sector controls and missing-session target horizons retain the engine's
  documented limitations. The actual Phase 4.1 data-source gate remains failed.
- Bloomberg has unresolved critical schema failures. No normalized security master or authorized
  prospective universe exists. The UI reports counts from raw diagnostics without elevating them.
- Historical machine snapshots, original execution times and most recorded checksums do not exist.
  Computing a current digest does not retrospectively prove integrity; the UI says **unrecorded**.
- Feature distribution/score distribution, expanded-signal daily diagnostics, a dedicated experiment
  registry UI, trade/risk drilldowns, and robustness comparisons are deferred. Existing supporting
  files can still be inspected in Reports.
- There is no job cancellation, automatic recovery/resumption, config editor, cloud deployment,
  external queue, multi-user access control, provider connection, brokerage connection, or live trading.
- The local adapters read whole dataframes for analysis. Caching and server pagination serve this
  checkout; thousands of securities and many concurrent experiments will benefit from partitioned
  reads/DuckDB or a separate query service and a proper worker queue.
