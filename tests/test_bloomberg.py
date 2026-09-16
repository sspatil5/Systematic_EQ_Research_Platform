from pathlib import Path

import pandas as pd
import pytest

from quant_trading.prospective.bloomberg import (
    BloombergImportError, import_bloomberg, normalize_ticker, parse_bloomberg_number,
)
from quant_trading.prospective.storage import ArtifactStore


HEADERS = ["Ticker", "Short Name", "Trd Status", "Avg Vol 40D", "Average Volume:D-30",
           "IPO Dt", "Market Cap", "Price:D-1", "Curncy", "Cntry Terrtry Of Dom", "Sec Type",
           "Primary Exchange MIC", "Prim Exch Nm", "BICS L4 Sub Ind Nm", "BICS L3 Ind Nm",
           "BICS L2 IG Nm", "BICS L1 Sect Nm", "FIGI"]


def row(**overrides):
    values = {"Ticker": "AAPL US Equity", "Short Name": "Apple", "Trd Status": "Y",
              "Avg Vol 40D": "5.20M", "Average Volume:D-30": "610.40k",
              "IPO Dt": "1980-12-12", "Market Cap": "3.33B", "Price:D-1": 100,
              "Curncy": "USD", "Cntry Terrtry Of Dom": "US", "Sec Type": "Common Stock",
              "Primary Exchange MIC": "XNAS", "Prim Exch Nm": "NASDAQ GS",
              "BICS L4 Sub Ind Nm": "Hardware", "BICS L3 Ind Nm": "Tech",
              "BICS L2 IG Nm": "Tech", "BICS L1 Sect Nm": "Technology", "FIGI": "BBG1"}
    values.update(overrides)
    return values


def config(tmp_path):
    path = tmp_path / "prospective.yaml"
    path.write_text(f'''experiment_id: SNM12M_V1_20260817
created_at: "2026-08-17T12:00:00-04:00"
timezone: America/New_York
provider: BLOOMBERG_MANUAL_EXPORT
universe:
  security_types: [COMMON_STOCK]
  allowed_exchanges: [NYSE, NASDAQ, NYSE_AMERICAN]
  minimum_price: 5
  minimum_trailing_dollar_volume: 20000000
  minimum_history_sessions: 252
  sector_required: true
portfolio: {{size: 10, rebalance_frequency: weekly_last_session, initial_equity: 30000, whole_shares: true, long_only: true, leverage: false}}
execution: {{mode: next_valid_session_open, cost_bps: 5, missing_open_policy: SKIP_AND_RECORD}}
cost_scenarios_bps: [0, 2, 5, 10, 20]
signals: {{primary: sector_neutral_momentum_12_1, challenger: combined_momentum_volatility}}
checkpoints_months: [3, 6, 12]
storage_root: {tmp_path / 'prospective'}
report_root: {tmp_path / 'reports'}
''')
    return path


def write_xlsx(path, rows, columns=HEADERS):
    pd.DataFrame(rows).reindex(columns=columns).to_excel(path, index=False)


def test_numeric_parser_and_malformed_values():
    assert parse_bloomberg_number("5.20M") == 5_200_000
    assert parse_bloomberg_number("610.40k") == 610_400
    assert parse_bloomberg_number("693.04M") == 693_040_000
    assert parse_bloomberg_number("3.33B") == 3_330_000_000
    assert pd.isna(parse_bloomberg_number("not a number"))


def test_ticker_mapping_is_explicit():
    assert normalize_ticker("AAPL US Equity")[:3] == ("AAPL", "AAPL", "DIRECT")
    assert normalize_ticker("BRK.B US Equity")[:3] == ("BRK.B", "BRK-B", "TRANSFORMED")
    assert normalize_ticker("BRK/A US Equity")[2] == "UNRESOLVED"
    assert normalize_ticker("AAPL")[2] == "UNRESOLVED"


def test_multifile_dedup_provenance_header_order_and_filters(tmp_path):
    inputs = tmp_path / "inputs"; inputs.mkdir()
    write_xlsx(inputs / "a_2026-08-24.xlsx", [row()])
    reordered = list(reversed(HEADERS))
    write_xlsx(inputs / "b_2026-08-24.xlsx", [row(), row(**{"FIGI":"BBG2", "Ticker":"BAD/A US Equity"})], reordered)
    before = {p.name: p.read_bytes() for p in inputs.glob("*.xlsx")}
    result = import_bloomberg("2026-08-24", inputs, config(tmp_path))
    frame = pd.read_parquet(result.snapshot_path).set_index("figi")
    assert len(frame) == 2 and frame.loc["BBG1", "source_files"] == "a_2026-08-24.xlsx;b_2026-08-24.xlsx"
    assert frame.loc["BBG1", "security_master_eligible"]
    assert frame.loc["BBG2", "security_master_exclusion_reason"] == "TICKER_UNRESOLVED"
    assert result.summary["exact_duplicates"] == 1
    assert before == {p.name: p.read_bytes() for p in inputs.glob("*.xlsx")}


def test_missing_critical_column_fails_and_registers_raw(tmp_path):
    inputs = tmp_path / "inputs"; inputs.mkdir()
    write_xlsx(inputs / "x_2026-08-24.xlsx", [row()], [x for x in HEADERS if x != "Primary Exchange MIC"])
    cfg = config(tmp_path)
    with pytest.raises(BloombergImportError, match="Primary Exchange MIC"):
        import_bloomberg("2026-08-24", inputs, cfg)
    assert not list((tmp_path / "prospective").glob("security_master/**/*.parquet"))
    assert "BLOOMBERG_RAW" in pd.read_csv(tmp_path / "prospective/manifest.csv").artifact_type.tolist()


def test_conflicting_figi_is_flagged(tmp_path):
    inputs = tmp_path / "inputs"; inputs.mkdir()
    write_xlsx(inputs / "x_2026-08-24.xlsx", [row(), row(**{"Ticker":"MSFT US Equity"})])
    result = import_bloomberg("2026-08-24", inputs, config(tmp_path))
    frame = pd.read_parquet(result.snapshot_path)
    assert result.summary["conflicting_figis"] == 1
    assert frame.security_master_exclusion_reason.eq("IDENTITY_CONFLICT").all()


def test_missing_figi_unknown_exchange_type_country_currency_status_sector(tmp_path):
    inputs = tmp_path / "inputs"; inputs.mkdir()
    bad = row(**{"FIGI": None, "Primary Exchange MIC":"ZZZZ", "Sec Type":"ETF",
                 "Cntry Terrtry Of Dom":"CA", "Curncy":"CAD", "Trd Status":"?",
                 "BICS L1 Sect Nm":None})
    write_xlsx(inputs / "x_2026-08-24.xlsx", [bad])
    result = import_bloomberg("2026-08-24", inputs, config(tmp_path))
    reasons = pd.read_parquet(result.snapshot_path).iloc[0].security_master_exclusion_reason
    for expected in ("MISSING_FIGI", "EXCHANGE_UNRESOLVED", "SECURITY_TYPE_NOT_ALLOWED",
                     "NON_US_COUNTRY", "NON_USD_CURRENCY", "TRADING_STATUS_UNKNOWN", "MISSING_SECTOR"):
        assert expected in reasons


def test_registered_source_hash_change_is_detected(tmp_path):
    source = tmp_path / "source.xlsx"; source.write_bytes(b"original")
    store = ArtifactStore(tmp_path / "prospective", "X")
    store.register_file(source, "BLOOMBERG_RAW", 1, "2026-08-24")
    source.write_bytes(b"changed")
    assert not store.verify().valid.all()


def test_filename_date_conflict_fails(tmp_path):
    inputs = tmp_path / "inputs"; inputs.mkdir()
    write_xlsx(inputs / "x_2026-08-23.xlsx", [row()])
    with pytest.raises(BloombergImportError, match="conflicts"):
        import_bloomberg("2026-08-24", inputs, config(tmp_path))


def test_bloomberg_import_does_not_apply_ohlcv_rules_or_create_stage_a(tmp_path):
    inputs = tmp_path / "inputs"; inputs.mkdir()
    write_xlsx(inputs / "x_2026-08-24.xlsx", [row(**{"Price:D-1": 1, "IPO Dt":"2026-08-01",
                                                        "Avg Vol 40D": 1})])
    result = import_bloomberg("2026-08-24", inputs, config(tmp_path))
    frame = pd.read_parquet(result.snapshot_path)
    assert frame.security_master_eligible.all()
    assert not list((tmp_path / "prospective/signals").glob("*"))
    assert not list((tmp_path / "prospective/orders").glob("*"))
    assert frame.experiment_id.eq("SNM12M_V1_20260817").all()


def test_no_brokerage_connectivity_added():
    text = Path("src/quant_trading/prospective/bloomberg.py").read_text().lower()
    assert not any(term in text for term in ("schwab", "oauth", "submit_order"))
