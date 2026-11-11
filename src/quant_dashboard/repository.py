"""Read-only adapters for verified repository artifacts, with no research reruns."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator
import yaml

from quant_trading.features.metadata import base_metadata
from quant_trading.risk.metrics import drawdown_series, performance_metrics
from quant_trading.prospective.storage import sha256_file
from quant_dashboard.schemas import Artifact, Dataset, Run


class Filters(BaseModel):
    run_id: str = Field(default="historical", max_length=80)
    strategy: Literal["primary", "challenger", "raw_momentum_benchmark"] = "primary"
    period: Literal["FULL", "DEVELOPMENT", "CONFIRMATION"] = "FULL"
    start: str | None = None
    end: str | None = None

    @model_validator(mode="after")
    def valid_dates(self):
        for value in (self.start, self.end):
            if value is not None:
                datetime.strptime(value, "%Y-%m-%d")
        if self.start and self.end and self.start > self.end:
            raise ValueError("Start date must be on or before end date")
        return self


def records(frame: pd.DataFrame) -> list[dict]:
    # Preserve the full Python float. DataFrame.to_json's default precision rounds
    # stored research statistics, which would violate artifact fidelity.
    return clean(frame.to_dict(orient="records"))


def clean(value):
    return json.loads(json.dumps(value, default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item),
                                 allow_nan=True), parse_constant=lambda _: None)


@lru_cache(maxsize=32)
def _read_frame(path: str, stamp: int, size: int, columns: tuple[str, ...] | None):
    del stamp, size
    target = Path(path)
    if target.suffix == ".parquet":
        return pd.read_parquet(target, columns=list(columns) if columns else None)
    return pd.read_csv(target, usecols=list(columns) if columns else None)


class Repository:
    def __init__(self, root: Path, store):
        self.root = root.resolve()
        self.store = store

    def read(self, path: Path, columns=None) -> pd.DataFrame:
        if not path.is_file():
            return pd.DataFrame()
        stat = path.stat()
        try:
            return _read_frame(str(path), stat.st_mtime_ns, stat.st_size,
                               tuple(columns) if columns else None).copy(deep=False)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    def config(self, run_id="historical") -> dict:
        if run_id == "historical":
            path = self.root / "config/research.yaml"
            return yaml.safe_load(path.read_text()) if path.exists() else {}
        return self.store.get(run_id)["config_snapshot"] or {}

    def public_config(self, payload):
        if isinstance(payload, dict):
            return {k: self.public_config(v) for k, v in payload.items()}
        if isinstance(payload, list):
            return [self.public_config(v) for v in payload]
        if isinstance(payload, str) and payload.startswith("/"):
            path = Path(payload)
            return str(path.relative_to(self.root)) if path.is_relative_to(self.root) else "[external path]"
        return payload

    def phase(self, run_id: str, phase: str) -> Path:
        if run_id == "historical":
            return self.root / "reports" / phase
        job = self.store.get(run_id)
        return self.store.run_dir(job["id"]) / "outputs" / phase

    def dataset_path(self, run_id="historical") -> Path:
        # New runs retain their original input path in the stored immutable configuration.
        config = self.config(run_id)
        path = Path(config.get("data", {}).get("processed_path", "data/processed/daily_panel.parquet"))
        return path if path.is_absolute() else self.root / path

    def frame(self, run_id, phase, filename):
        return self.read(self.phase(run_id, phase) / filename)

    def window(self, frame, filters: Filters, date_column=None):
        if frame.empty:
            return frame
        dates = pd.to_datetime(frame[date_column]) if date_column else pd.to_datetime(frame.index.get_level_values("date"))
        config = self.config(filters.run_id).get("alpha_research", {})
        mask = np.ones(len(frame), dtype=bool)
        if filters.period == "DEVELOPMENT":
            mask &= dates <= pd.Timestamp(config.get("development_end", "2021-12-31"))
        elif filters.period == "CONFIRMATION":
            mask &= dates >= pd.Timestamp(config.get("confirmation_start", "2022-01-01"))
        if filters.start:
            mask &= dates >= pd.Timestamp(filters.start)
        if filters.end:
            mask &= dates <= pd.Timestamp(filters.end)
        return frame.loc[mask]

    def dataset(self, filters: Filters) -> Dataset:
        panel = self.read(self.dataset_path(filters.run_id))
        if panel.empty:
            return Dataset(available=False, warnings=["Canonical market panel unavailable. Build it with the existing download-data CLI."])
        panel = self.window(panel, filters)
        if panel.empty:
            return Dataset(available=True, warnings=["No market observations in the selected period."])
        dates = panel.index.get_level_values("date")
        tickers = panel.index.get_level_values("ticker")
        end = dates.max().date()
        age = (datetime.now(ZoneInfo("America/New_York")).date() - end).days
        sectors = self.sectors()
        warnings = ["Static present-day universe: survivorship and selection bias apply. Sector labels are not point-in-time."]
        if age > 7:
            warnings.append(f"Market data ends {end.isoformat()} ({age} calendar days old).")
        return Dataset(available=True, start=str(dates.min().date()), end=str(end), rows=len(panel),
                       securities=tickers.nunique(), coverage=len(panel) / (dates.nunique() * tickers.nunique()),
                       freshness_days=age, sectors=sorted(set(sectors.values())), warnings=warnings)

    def sectors(self):
        path = self.root / "data/processed/sector_mapping.csv"
        if not path.exists():
            path = self.root / "reports/phase3_5/sector_mapping.csv"
        table = self.read(path)
        return dict(zip(table.ticker, table.sector)) if not table.empty else {}

    def universe(self, filters, search="", sector="", minimum_liquidity=0, eligible_only=False,
                 sort="ticker", descending=False, page=1, page_size=25):
        panel = self.window(self.read(self.dataset_path(filters.run_id)), filters)
        if panel.empty:
            return dict(items=[], total=0, page=page, page_size=page_size,
                        note="No canonical observations for this selection.")
        frame = panel.reset_index()
        sessions = frame.date.nunique()
        grouped = frame.groupby("ticker")
        result = grouped.agg(start=("date", "min"), end=("date", "max"), observations=("date", "size"),
                             latest_close=("close", "last"))
        result["missing_fraction"] = 1 - result.observations / sessions
        result["missing_cells"] = grouped[["open", "high", "low", "close", "volume"]].apply(lambda x: int(x.isna().sum().sum()))
        result["sector"] = result.index.map(self.sectors()).fillna("Unavailable")
        config = self.config(filters.run_id)
        feature_path = Path(config.get("features", {}).get("output_path", "data/processed/features.parquet"))
        if not feature_path.is_absolute():
            feature_path = self.root / feature_path
        features = self.read(feature_path, ["avg_dollar_volume_20"])
        features = self.window(features, filters)
        result["dollar_volume_20"] = features.groupby(level="ticker").last().get("avg_dollar_volume_20") if not features.empty else np.nan
        floor = config.get("backtest", {}).get("liquidity_floor")
        result["liquidity_eligible"] = result.dollar_volume_20.ge(floor) if floor is not None else None
        # No valid security master exists: never infer authoritative identifiers or exchanges.
        result["exchange"] = None
        result["security_id"] = None
        result = result.reset_index()
        if search:
            result = result.loc[result.ticker.str.contains(search, case=False, regex=False)]
        if sector:
            result = result.loc[result.sector == sector]
        if minimum_liquidity:
            result = result.loc[result.dollar_volume_20 >= minimum_liquidity]
        if eligible_only:
            result = result.loc[result.liquidity_eligible == True]  # noqa: E712
        if sort not in result.columns:
            raise ValueError("Unsupported universe sort column")
        result = result.sort_values(sort, ascending=not descending, na_position="last")
        return dict(items=records(result.iloc[(page-1)*page_size:page*page_size]), total=len(result), page=page,
                    page_size=page_size, columns=list(result.columns),
                    note="Missing coverage includes pre-listing sessions against the selected panel calendar. Liquidity eligibility uses the last available 20-session dollar volume and the configured backtest floor; it is not security-master approval. Identifiers and exchanges are unavailable after the failed import.")

    def backtest(self, filters: Filters):
        config = self.config(filters.run_id)
        base = dict(available=False, run_id=filters.run_id, strategy=filters.strategy, period=filters.period,
                    configuration=self.public_config(config.get("backtest", {})),
                    configuration_provenance="Current reference YAML; original machine-readable run snapshot unavailable." if filters.run_id == "historical" else "Immutable dashboard run snapshot.",
                    warnings=["Historical simulation on a survivorship-biased static universe. Not live performance."])
        freeze = self.phase(filters.run_id, "phase4") / "research_freeze.md"
        if freeze.exists():
            base["freeze_definition"] = freeze.read_text()
        summary = self.frame(filters.run_id, "phase4", "strategy_summary.csv")
        daily = self.frame(filters.run_id, "phase4", f"{filters.strategy}_daily.parquet")
        if summary.empty or daily.empty:
            base["warnings"].append("No saved backtest results for this run. Choose the repository artifacts or a completed backtest run.")
            return base
        saved = summary.loc[(summary.strategy == filters.strategy) & (summary["sample"] == filters.period)]
        if saved.empty:
            base["warnings"].append("No saved summary for the selected strategy and period.")
            return base
        metric = records(saved)[0]
        capital = metric["ending_equity"] / (1 + metric["total_return"])
        base["initial_capital"] = capital
        daily = daily.loc[(daily.index >= metric["start"]) & (daily.index <= metric["end"])]
        daily = self.window(daily, filters)
        if daily.empty:
            base["warnings"].append("No backtest observations in this date range.")
            return base
        benchmarks = self.frame(filters.run_id, "phase4", "benchmarks.csv")
        if benchmarks.empty:
            base["warnings"].append("Saved benchmark returns are missing; comparison and metrics are unavailable.")
            return base
        benchmarks = benchmarks.set_index(pd.to_datetime(benchmarks.date)).reindex(daily.index)
        if benchmarks[["spy", "equal_weight"]].isna().any().any():
            base["warnings"].append("Benchmark dates do not cover this backtest; results are unavailable.")
            return base
        source = "Stored strategy_summary.csv; values preserved exactly."
        if str(daily.index.min().date()) != metric["start"] or str(daily.index.max().date()) != metric["end"]:
            trades = self.frame(filters.run_id, "phase4", f"{filters.strategy}_trades.parquet")
            trade_count = int(pd.to_datetime(trades.execution_date).isin(daily.index).sum()) if not trades.empty else 0
            metric = clean(performance_metrics(daily.net_return, daily.equity, benchmarks.spy,
                           cash_weight=daily.cash_weight, turnover=daily.turnover,
                           total_costs=float(daily.daily_cost.sum()), trade_count=trade_count))
            years = len(daily) / 252
            metric.update(ending_equity=capital * (1 + metric["total_return"]),
                          spy_cagr=float((1 + benchmarks.spy).prod() ** (1 / years) - 1),
                          equal_weight_cagr=float((1 + benchmarks.equal_weight).prod() ** (1 / years) - 1))
            source = "Date-filtered saved returns; computed with existing quant_trading.risk.metrics.performance_metrics."
        curve = pd.DataFrame(index=daily.index)
        curve["portfolio"] = (1 + daily.net_return).cumprod() * capital
        curve["spy"] = (1 + benchmarks.spy).cumprod() * capital
        curve["equal_weight"] = (1 + benchmarks.equal_weight).cumprod() * capital
        curve["drawdown"] = drawdown_series(daily.equity)
        r = daily.net_return
        curve["rolling_sharpe"] = r.rolling(126).mean() / r.rolling(126).std(ddof=1) * np.sqrt(252)
        curve["rolling_volatility"] = r.rolling(126).std(ddof=1) * np.sqrt(252)
        curve["rolling_beta"] = r.rolling(126).cov(benchmarks.spy) / benchmarks.spy.rolling(126).var()
        curve.index.name = "date"
        monthly = ((1 + r).groupby(r.index.to_period("M")).prod() - 1).rename("return").reset_index()
        monthly["year"] = monthly.date.dt.year
        monthly["month"] = monthly.date.dt.month
        monthly["date"] = monthly.date.astype(str)
        annual = pd.DataFrame({"portfolio": (1+r).groupby(r.index.year).prod()-1,
                               "spy": (1+benchmarks.spy).groupby(daily.index.year).prod()-1,
                               "equal_weight": (1+benchmarks.equal_weight).groupby(daily.index.year).prod()-1}).rename_axis("year").reset_index()
        base.update(available=True, metrics=metric, metrics_source=source, curve=records(curve.reset_index()),
                    monthly=records(monthly), annual=records(annual))
        return base

    def signals(self, filters, signal=None):
        score = self.frame(filters.run_id, "phase3", "signal_scorecard.csv")
        dev = self.frame(filters.run_id, "phase3_5", "development_results.csv")
        confirm = self.frame(filters.run_id, "phase3_5", "confirmation_results.csv")
        config = self.config(filters.run_id).get("features", {})
        metadata = base_metadata(tuple(config.get("return_lookbacks", [])), tuple(config.get("moving_average_windows", [])), tuple(config.get("volatility_windows", [])))
        if filters.period != "FULL":
            score = dev.copy() if filters.period == "DEVELOPMENT" else confirm.copy()
            if not score.empty:
                score["fdr_q_value"] = score.family_fdr_q_value
                score["raw_p_value"] = score.p_value
                score["classification"] = "Exploratory post-selection evidence"
        if not score.empty:
            score = score.copy()
            score["description"] = score.signal.map(lambda s: metadata[s].description if s in metadata else "Stored Phase 3.5 signal; see frozen hypothesis registry for definition.")
            score["lookback"] = score.signal.map(lambda s: metadata[s].lookback_days if s in metadata else None)
            for name, frame in (("development_ic", dev), ("confirmation_ic", confirm)):
                score[name] = score.signal.map(dict(zip(frame.signal, frame.mean_rank_ic))) if not frame.empty else np.nan
        selected = signal or (str(score.iloc[0].signal) if not score.empty else "")
        daily = self.frame(filters.run_id, "phase3", "daily_ic.parquet")
        if not daily.empty:
            daily = self.window(daily.loc[daily.signal == selected], filters, "date")
        quantiles = self.frame(filters.run_id, "phase3", "quantile_returns.csv")
        if not quantiles.empty:
            quantiles = self.window(quantiles.loc[quantiles.signal == selected], filters, "date")
            quantiles = quantiles[["q1", "q2", "q3", "q4", "q5"]].mean().rename_axis("quantile").reset_index(name="return")
        if quantiles.empty and not score.empty:
            row = score.loc[score.signal == selected]
            if not row.empty:
                quantiles = pd.DataFrame([{"quantile": f"q{i}", "return": row.iloc[0].get(f"q{i}_return")} for i in range(1,6)])
        decay = self.frame(filters.run_id, "phase3", "signal_decay.csv") if filters.period == "FULL" else pd.DataFrame()
        if not decay.empty:
            decay = decay.loc[decay.signal == selected]
        correlations = self.frame(filters.run_id, "phase3", "signal_correlations.csv") if filters.period == "FULL" else pd.DataFrame()
        if not correlations.empty:
            correlations = correlations.rename(columns={correlations.columns[0]: "signal"})
        return dict(available=not score.empty, run_id=filters.run_id, period=filters.period,
                    source="Phase 3 exploratory diagnostics" if filters.period == "FULL" else f"Phase 3.5 {filters.period.lower()} stored results",
                    scorecard=records(score), daily_ic=records(daily), decay=records(decay), quantiles=records(quantiles),
                    correlations=records(correlations),
                    note="Scorecard inference uses the complete stored sample; date filters apply only to IC and quantile series. Decay and correlations use the full Phase 3 sample and are hidden for split periods. Quantiles are forward-return diagnostics, not executable returns. Statistical significance does not establish economic significance or validated alpha.")

    def import_status(self):
        reports = sorted((self.root / "reports/phase5").glob("bloomberg_import_*.md"))
        sources = sorted(p.name for p in (self.root / "src/quant_trading/data/bloomberg").glob("*.xlsx"))
        audit = self.read(self.root / "data/prospective/audit_log.csv")
        history = audit.loc[audit.event_type.str.startswith("BLOOMBERG", na=False)].tail(30) if not audit.empty else audit
        result = dict(status="unavailable", source_files=sources, history=records(history), errors=[], summary={})
        if reports:
            report = reports[-1]
            text = report.read_text()
            match = re.search(r"```json\s*(.*?)\s*```", text, re.S)
            summary = json.loads(match.group(1)) if match else {}
            failures = summary.get("missing_critical_columns", {})
            errors = [f"{name}: missing {', '.join(columns)}" for name, columns in failures.items()]
            result.update(status="failed" if failures or "FAILED" in text else summary.get("coverage_status", "recorded").lower(),
                          snapshot_date=report.stem.removeprefix("bloomberg_import_"), summary=summary, errors=errors)
        return result

    def recorded_hashes(self):
        hashes = {}
        manifests = [self.root / "data/prospective/manifest.csv"]
        for p in manifests:
            frame = self.read(p)
            if not frame.empty:
                for row in frame.itertuples():
                    relative = Path(row.filename)
                    target = self.root / relative if str(relative).startswith("src/") else p.parent / relative
                    hashes[str(target.resolve())] = str(row.sha256)
        for p in self.store.runs_root.glob("*/checksums.json"):
            for relative, digest in json.loads(p.read_text()).items():
                hashes[str((p.parent / relative).resolve())] = digest
        return hashes

    def artifact_index(self, run_id="historical"):
        roots = [self.root / "reports", self.root / "config", self.root / "data/processed",
                 self.root / "data/prospective", self.root / "src/quant_trading/data/bloomberg"] if run_id == "historical" else [self.store.run_dir(self.store.get(run_id)["id"])]
        allowed = {".csv", ".parquet", ".md", ".json", ".yaml", ".png", ".svg", ".pdf", ".xlsx", ".docx", ".log"}
        hashes = self.recorded_hashes()
        result = {}
        for folder in roots:
            if not folder.exists():
                continue
            for candidate in folder.rglob("*"):
                if candidate.suffix not in allowed or candidate.name.startswith((".", "~$")) or not candidate.is_file():
                    continue
                path = candidate.resolve()
                # Reject symlinks escaping the approved directory, including within the repo.
                if not path.is_relative_to(folder.resolve()) or not path.is_relative_to(self.root):
                    continue
                relative = str(path.relative_to(self.root))
                identifier = hashlib.sha256(relative.encode()).hexdigest()[:24]
                stat = path.stat()
                parts = candidate.relative_to(folder).parts
                group = parts[0] if folder.name == "reports" and len(parts) > 1 else folder.name
                metadata = Artifact(id=identifier, name=path.name, location=relative, group=group, kind=path.suffix[1:],
                                    size=stat.st_size, modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                                    recorded_sha256=hashes.get(str(path)))
                result[identifier] = (path, metadata)
        return result

    def artifact(self, identifier, run_id="historical"):
        result = self.artifact_index(run_id).get(identifier)
        if result is None:
            raise KeyError("Artifact not found in this research context")
        return result

    def preview(self, identifier, run_id):
        path, metadata = self.artifact(identifier, run_id)
        result = dict(artifact=metadata)
        if path.suffix in {".csv", ".parquet"}:
            if path.suffix == ".parquet":
                import pyarrow.parquet as pq
                source = pq.ParquetFile(path)
                frame = next(source.iter_batches(batch_size=100), None)
                frame = frame.to_pandas() if frame is not None else pd.DataFrame()
                count = source.metadata.num_rows
            else:
                frame = pd.read_csv(path, nrows=100)
                count = None
            result.update(rows=records(frame), columns=list(frame.columns), total_rows=count, truncated=count > 100 if count is not None else len(frame) == 100)
        elif path.suffix in {".md", ".json", ".yaml", ".log"}:
            with path.open() as handle:
                text = handle.read(100001)
            result.update(text=text[:100000], truncated=len(text) > 100000)
        return result

    def verify(self, identifier, run_id):
        path, meta = self.artifact(identifier, run_id)
        actual = sha256_file(path)
        return dict(id=identifier, actual_sha256=actual, recorded_sha256=meta.recorded_sha256,
                    status="unrecorded" if not meta.recorded_sha256 else "verified" if actual == meta.recorded_sha256 else "mismatch")

    def historical_runs(self):
        runs = []
        for phase, label in [("phase3", "Signal diagnostics"), ("phase3_5", "Alpha development / confirmation"), ("phase4", "Realistic backtest")]:
            folder = self.root / "reports" / phase
            if folder.exists() and any(folder.iterdir()):
                runs.append(Run(id=f"historical-{phase}", label=label, stage=phase, status="historical",
                                classification="Existing historical artifacts; original execution timestamp and machine configuration not recorded.",
                                output_location=f"reports/{phase}"))
        return runs
