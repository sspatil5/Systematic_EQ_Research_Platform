"""Fail-closed ingestion of immutable Bloomberg security-master exports."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from quant_trading.prospective.config import load_prospective_config
from quant_trading.prospective.storage import ArtifactStore, sha256_file

HEADER_MAP = {
    "Ticker": "ticker_raw", "Short Name": "short_name", "Trd Status": "trading_status",
    "Avg Vol 40D": "avg_volume_40d_raw", "Average Volume:D-30": "avg_volume_30d_raw",
    "IPO Dt": "ipo_date", "Market Cap": "market_cap_raw", "Price:D-1": "price_d1_raw",
    "Curncy": "currency", "Cntry Territory Of Dom": "country",
    "Cntry Terrtry Of Dom": "country", "Sec Type": "security_type",
    "Primary Exchange MIC": "primary_exchange_mic", "Prim Exch Nm": "primary_exchange_name",
    "BICS L4 Sub Ind Nm": "bics_sub_industry", "BICS L3 Ind Nm": "bics_industry",
    "BICS L2 IG Nm": "bics_industry_group", "BICS L1 Sect Nm": "bics_sector", "FIGI": "figi",
}
CRITICAL = {"Ticker", "Trd Status", "Price:D-1", "Curncy", "Sec Type",
            "Primary Exchange MIC", "Prim Exch Nm", "BICS L1 Sect Nm", "FIGI"}
COUNTRY_HEADERS = {"Cntry Territory Of Dom", "Cntry Terrtry Of Dom"}
MATERIAL = ["ticker", "security_type", "primary_exchange_mic", "bics_sector", "country", "currency"]
EXCHANGE_MAP = {
    "XNAS": "NASDAQ", "XNGS": "NASDAQ", "XNMS": "NASDAQ", "XNCM": "NASDAQ",
    "XNYS": "NYSE", "XASE": "NYSE_AMERICAN",
}
NAME_DIAGNOSTIC_MAP = {
    "NASDAQ GS": "NASDAQ", "NASDAQ GM": "NASDAQ", "NASDAQ CM": "NASDAQ",
    "New York": "NYSE", "NYSEAmerican": "NYSE_AMERICAN",
}


class BloombergImportError(ValueError):
    pass


@dataclass
class ImportResult:
    snapshot_path: Path | None
    report_path: Path
    coverage_status: str
    summary: dict


def parse_bloomberg_number(value):
    if value is None or pd.isna(value) or (isinstance(value, str) and not value.strip()):
        return np.nan
    if isinstance(value, (int, float, np.number)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip().replace(",", "")
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([kKmMbB]?)", text)
    if not match:
        return np.nan
    multiplier = {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[match.group(2).lower()]
    return float(match.group(1)) * multiplier


def normalize_ticker(value):
    raw = "" if pd.isna(value) else str(value).strip()
    match = re.fullmatch(r"([A-Z0-9]+(?:[./-][A-Z0-9]+)?) US Equity", raw)
    if not match:
        return "", "", "UNRESOLVED", "Ticker is not unambiguous Bloomberg US Equity syntax"
    ticker = match.group(1)
    if "/" in ticker or "-" in ticker:
        return ticker, "", "UNRESOLVED", "Provider share-class mapping requires explicit review"
    provider = ticker.replace(".", "-")
    status = "DIRECT" if provider == ticker else "TRANSFORMED"
    return ticker, provider, status, "Exact syntax mapping"


def _filename_date(path: Path):
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", path.name)
    return date.fromisoformat(match.group(1)) if match else None


def _read_sources(input_dir: Path, snapshot_date: date):
    files = sorted(input_dir.glob("*.xlsx"))
    if not files:
        raise BloombergImportError(f"No XLSX files found in {input_dir}")
    frames, metadata, missing_by_file = [], [], {}
    ingested = datetime.now(timezone.utc).isoformat()
    for path in files:
        embedded = _filename_date(path)
        if embedded and embedded != snapshot_date:
            raise BloombergImportError(f"Filename date {embedded} conflicts with {snapshot_date}: {path.name}")
        frame = pd.read_excel(path, dtype=object)
        missing = sorted(CRITICAL - set(frame.columns))
        if not COUNTRY_HEADERS.intersection(frame.columns):
            missing.append("Cntry Territory Of Dom")
        missing_by_file[path.name] = missing
        frame["source_file"] = path.name
        frame["source_row_number"] = np.arange(2, len(frame) + 2)
        frame["snapshot_date"] = snapshot_date.isoformat()
        frame["ingestion_timestamp"] = ingested
        frames.append(frame)
        metadata.append({"filename": path.name, "path": path, "sha256": sha256_file(path),
                         "file_size": path.stat().st_size, "row_count": len(frame)})
    return files, frames, metadata, missing_by_file


def _diagnostics(raw: pd.DataFrame, report_root: Path):
    report_root.mkdir(parents=True, exist_ok=True)
    for column in ("Primary Exchange MIC", "Prim Exch Nm", "Sec Type"):
        if column not in raw:
            raw[column] = np.nan
    exchange = raw.groupby(["Primary Exchange MIC", "Prim Exch Nm"], dropna=False).size().rename("row_count").reset_index()
    exchange.columns = ["primary_exchange_mic", "primary_exchange_name", "row_count"]
    exchange["exchange_family"] = exchange.primary_exchange_mic.map(EXCHANGE_MAP).fillna("UNRESOLVED")
    exchange["allowed"] = exchange.exchange_family.isin({"NASDAQ", "NYSE", "NYSE_AMERICAN"})
    exchange["mapping_status"] = np.where(exchange.allowed, "MAPPED_BY_MIC", "UNRESOLVED")
    exchange.to_csv(report_root / "bloomberg_exchange_mapping.csv", index=False)
    types = raw.groupby("Sec Type", dropna=False).size().rename("row_count").reset_index()
    types.columns = ["security_type", "row_count"]
    types["allowed"] = types.security_type.eq("Common Stock")
    types["mapping_status"] = np.where(types.allowed, "MAPPED", "NOT_ALLOWED")
    types.to_csv(report_root / "bloomberg_security_types.csv", index=False)
    return exchange, types


def _normalize(raw: pd.DataFrame, experiment_id: str):
    frame = raw.rename(columns=HEADER_MAP).copy()
    mapped = frame.ticker_raw.map(normalize_ticker)
    frame[["ticker", "provider_ticker", "ticker_mapping_status", "ticker_mapping_reason"]] = pd.DataFrame(mapped.tolist(), index=frame.index)
    for field in ("price_d1", "market_cap", "avg_volume_40d", "avg_volume_30d"):
        frame[field] = frame[f"{field}_raw"].map(parse_bloomberg_number)
    frame["exchange_family"] = frame.primary_exchange_mic.map(EXCHANGE_MAP).fillna("UNRESOLVED")
    frame["experiment_id"] = experiment_id
    return frame


def _deduplicate(frame: pd.DataFrame):
    data_cols = [c for c in frame.columns if c not in {"source_file", "source_row_number", "ingestion_timestamp"}]
    exact_mask = frame.duplicated(data_cols, keep=False)
    exact_duplicates = int(frame.duplicated(data_cols).sum())
    conflicts = set()
    valid = frame.loc[frame.figi.notna() & frame.figi.astype(str).str.strip().ne("")]
    for figi, group in valid.groupby("figi"):
        if any(group[col].fillna("<NA>").astype(str).nunique() > 1 for col in MATERIAL):
            conflicts.add(figi)
    rows = []
    missing_keys = pd.Series("__MISSING_" + frame.index.astype(str), index=frame.index)
    keys = frame.figi.where(frame.figi.notna() & frame.figi.astype(str).str.strip().ne(""), missing_keys)
    for _, group in frame.groupby(keys, sort=False):
        row = group.iloc[0].copy()
        row["source_files"] = ";".join(sorted(group.source_file.unique()))
        row["source_provenance"] = json.dumps(group[["source_file", "source_row_number"]].to_dict("records"), sort_keys=True)
        rows.append(row)
    return pd.DataFrame(rows), exact_duplicates, conflicts, int(exact_mask.sum())


def _eligibility(frame: pd.DataFrame, conflicts: set[str]):
    def reasons(row):
        out = []
        if pd.isna(row.figi) or not str(row.figi).strip(): out.append("MISSING_FIGI")
        elif row.figi in conflicts: out.append("IDENTITY_CONFLICT")
        if row.ticker_mapping_status == "UNRESOLVED": out.append("TICKER_UNRESOLVED")
        if row.exchange_family == "UNRESOLVED": out.append("EXCHANGE_UNRESOLVED")
        elif row.exchange_family not in {"NASDAQ", "NYSE", "NYSE_AMERICAN"}: out.append("EXCHANGE_NOT_ALLOWED")
        if row.security_type != "Common Stock": out.append("SECURITY_TYPE_NOT_ALLOWED")
        if row.country != "US": out.append("NON_US_COUNTRY")
        if row.currency != "USD": out.append("NON_USD_CURRENCY")
        if row.trading_status == "N": out.append("TRADING_STATUS_INVALID")
        elif row.trading_status != "Y": out.append("TRADING_STATUS_UNKNOWN")
        if pd.isna(row.bics_sector) or not str(row.bics_sector).strip(): out.append("MISSING_SECTOR")
        return out
    all_reasons = frame.apply(reasons, axis=1)
    frame["security_master_exclusion_reason"] = all_reasons.map(lambda x: ";".join(x))
    frame["security_master_eligible"] = all_reasons.map(lambda x: not x)
    return frame


def import_bloomberg(snapshot_date: str, input_dir: str | Path,
                     config_path="config/prospective.yaml") -> ImportResult:
    supplied_date = date.fromisoformat(snapshot_date)
    config = load_prospective_config(config_path)
    store = ArtifactStore(config.storage_root, config.experiment_id)
    store.audit("BLOOMBERG_IMPORT_STARTED", snapshot_date, "bloomberg-import", "STARTED")
    files, frames, metadata, missing = _read_sources(Path(input_dir), supplied_date)
    for item in metadata:
        store.register_file(item["path"], "BLOOMBERG_RAW", item["row_count"], snapshot_date)
        store.audit("BLOOMBERG_RAW_REGISTERED", snapshot_date, "bloomberg-import", "SUCCESS", [item["path"]])
    union_columns = sorted(set().union(*(set(f.columns) for f in frames)))
    raw = pd.concat([f.reindex(columns=union_columns) for f in frames], ignore_index=True)
    exchange, types = _diagnostics(raw, config.report_root)
    fatal = {name: cols for name, cols in missing.items() if cols}
    summary = {"source_files": [{k: v for k, v in item.items() if k != "path"} for item in metadata],
               "combined_raw_rows": len(raw), "missing_critical_columns": fatal}
    # Compute non-authorizing diagnostics even when schema validation must fail.
    diagnostic = _normalize(raw, config.experiment_id)
    diagnostic_deduped, exact_duplicates, conflicts, exact_rows = _deduplicate(diagnostic)
    valid_figis = diagnostic.figi.notna() & diagnostic.figi.astype(str).str.strip().ne("")
    figi_counts = diagnostic.loc[valid_figis, "figi"].value_counts()
    summary.update({
        "exact_duplicates": exact_duplicates, "exact_duplicate_rows": exact_rows,
        "unique_figis": int(diagnostic.loc[valid_figis, "figi"].nunique()),
        "missing_figis": int((~valid_figis).sum()),
        "duplicate_figis": int(figi_counts.gt(1).sum()), "conflicting_figis": len(conflicts),
        "unique_normalized_tickers": int(diagnostic.ticker.replace("", np.nan).nunique()),
        "ticker_mapping_success_rate": float(diagnostic.ticker_mapping_status.ne("UNRESOLVED").mean()),
        "exchange_pairs": exchange.fillna("<MISSING>").to_dict("records"),
        "security_types": types.fillna("<MISSING>").to_dict("records"),
        "country_distribution": raw["Cntry Terrtry Of Dom"].fillna("<MISSING>").value_counts().to_dict(),
        "currency_distribution": raw["Curncy"].fillna("<MISSING>").value_counts().to_dict(),
        "trading_status_distribution": raw["Trd Status"].fillna("<MISSING>").value_counts().to_dict(),
        "sector_distribution": raw["BICS L1 Sect Nm"].fillna("<MISSING>").value_counts().to_dict(),
        "missing_sector": int(raw["BICS L1 Sect Nm"].isna().sum()),
        "missing_price": int(raw["Price:D-1"].isna().sum()),
        "overlapping_figis": int(sum(
            group.source_file.nunique() > 1
            for _, group in diagnostic.loc[valid_figis].groupby("figi")
        )),
    })
    report_path = config.report_root / f"bloomberg_import_{snapshot_date}.md"
    if fatal:
        lines = [f"# Bloomberg import — {snapshot_date}", "", "Import status: **FAILED — CRITICAL SCHEMA MISSING**", "",
                 "No normalized security-master snapshot was created.", "", "## Source files", ""]
        lines += [f"- `{x['filename']}`: {x['row_count']:,} rows, {x['file_size']:,} bytes, SHA-256 `{x['sha256']}`" for x in metadata]
        lines += ["", "## Critical schema failures", ""] + [f"- `{name}`: missing {', '.join(cols)}" for name, cols in fatal.items()]
        lines += ["", "## Non-authorizing diagnostics", "", "```json",
                  json.dumps(summary, indent=2, default=str), "```", "",
                  "Exchange and security-type diagnostic CSVs were written; blank MICs remain unresolved."]
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        store.audit("BLOOMBERG_IMPORT_FAILED", snapshot_date, "bloomberg-import", "INVALID",
                    [report_path], errors=json.dumps(fatal, sort_keys=True))
        failures = "; ".join(f"{name}: {', '.join(cols)}" for name, cols in fatal.items())
        raise BloombergImportError(f"Critical Bloomberg schema validation failed: {failures}")
    store.audit("BLOOMBERG_SCHEMA_VALIDATED", snapshot_date, "bloomberg-import", "SUCCESS")
    normalized = diagnostic
    deduped = diagnostic_deduped
    deduped = _eligibility(deduped, conflicts)
    duplicate_figis = int(figi_counts.gt(1).sum())
    family_counts = deduped.exchange_family.value_counts().to_dict()
    coverage = "COMPLETE" if all(family_counts.get(x, 0) >= 25 for x in ("NASDAQ", "NYSE", "NYSE_AMERICAN")) else "INCOMPLETE"
    output = store.write_frame(f"security_master/processed/security_master_{snapshot_date}.parquet", deduped,
                               "BLOOMBERG_SECURITY_MASTER", snapshot_date)
    summary.update({"exact_duplicates": exact_duplicates, "exact_duplicate_rows": exact_rows,
                    "unique_figis": int(deduped.figi.nunique()), "missing_figis": int(deduped.figi.isna().sum()),
                    "duplicate_figis": duplicate_figis, "conflicting_figis": len(conflicts),
                    "unique_normalized_tickers": int(deduped.ticker.replace("", np.nan).nunique()),
                    "ticker_mapping_success_rate": float(deduped.ticker_mapping_status.ne("UNRESOLVED").mean()),
                    "eligible": int(deduped.security_master_eligible.sum()), "coverage_status": coverage})
    report_path.write_text(f"# Bloomberg import — {snapshot_date}\n\n```json\n{json.dumps(summary, indent=2, default=str)}\n```\n", encoding="utf-8")
    store.audit("BLOOMBERG_SECURITY_MASTER_CREATED", snapshot_date, "bloomberg-import", "SUCCESS", [output])
    store.audit("BLOOMBERG_COVERAGE_VALIDATED", snapshot_date, "bloomberg-import",
                "SUCCESS" if coverage == "COMPLETE" else "INVALID")
    return ImportResult(output, report_path, coverage, summary)
