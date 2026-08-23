from pathlib import Path
import pandas as pd
import pytest

from quant_trading.prospective.config import ProspectiveConfig
from quant_trading.prospective.events import (
    eligible_universe, parallel_cost_accounting, stage_a, stage_b, validate_signal_timing,
    validate_benchmark_alignment,
)
from quant_trading.prospective.storage import ArtifactStore


def _config(tmp_path):
    return ProspectiveConfig.model_validate({
        "experiment_id":"TEST_V1", "created_at":"2026-08-17T12:00:00-04:00",
        "timezone":"America/New_York", "provider":"SYNTHETIC_TEST",
        "universe":{"security_types":["COMMON_STOCK"], "allowed_exchanges":["NYSE"],
                    "minimum_price":5, "minimum_trailing_dollar_volume":20_000_000,
                    "minimum_history_sessions":252, "sector_required":True},
        "portfolio":{"size":1, "rebalance_frequency":"weekly_last_session", "initial_equity":30_000,
                     "whole_shares":True, "long_only":True, "leverage":False},
        "execution":{"mode":"next_valid_session_open", "cost_bps":5,
                     "missing_open_policy":"SKIP_AND_RECORD"},
        "cost_scenarios_bps":[0,2,5,10,20],
        "signals":{"primary":"sector_neutral_momentum_12_1",
                   "challenger":"combined_momentum_volatility"},
        "checkpoints_months":[3,6,12], "storage_root":str(tmp_path),
        "report_root":str(tmp_path / "reports"),
    })


def _inputs():
    universe = pd.DataFrame([
        {"ticker":"A", "security_id":"ID_A", "exchange":"NYSE", "security_type":"COMMON_STOCK",
         "sector":"Tech", "price":100., "avg_dollar_volume_20":50_000_000., "history_sessions":300},
        {"ticker":"B", "security_id":"ID_B", "exchange":"NYSE", "security_type":"COMMON_STOCK",
         "sector":"Health", "price":20., "avg_dollar_volume_20":10_000_000., "history_sessions":300},
    ])
    market = pd.DataFrame({"date":pd.to_datetime(["2026-08-14", "2026-08-14"]),
                           "ticker":["A","B"], "open":[99.,20.], "high":[101.,21.],
                           "low":[98.,19.], "close":[100.,20.], "volume":[1_000_000,1_000_000]})
    signals = pd.DataFrame({"ticker":["A","B"], "momentum_12_1":[2.,1.],
        "sector_neutral_momentum_12_1":[2.,1.], "residual_volatility_beta":[1.,2.],
        "combined_momentum_volatility":[2.,1.]})
    return universe, market, signals


def _stage(tmp_path):
    config = _config(tmp_path); store = ArtifactStore(tmp_path, config.experiment_id)
    universe, market, signals = _inputs()
    stage_a(store, config, "2026-08-14", universe, market, signals)
    return config, store


def test_snapshot_immutability(tmp_path):
    store = ArtifactStore(tmp_path, "X")
    store.write_frame("signals/x.parquet", pd.DataFrame({"x":[1]}), "SIGNAL")
    with pytest.raises(FileExistsError): store.write_frame("signals/x.parquet", pd.DataFrame({"x":[2]}), "SIGNAL")


def test_hash_integrity_detects_modification(tmp_path):
    store = ArtifactStore(tmp_path, "X"); path = store.write_json("account/x.json", {"x":1}, "STATE")
    path.write_text("changed", encoding="utf-8")
    assert not store.verify().valid.all()


def test_signal_timing_accepts_same_day():
    validate_signal_timing("2026-08-14", "2026-08-14")


def test_future_data_fails_before_snapshot(tmp_path):
    config = _config(tmp_path); store = ArtifactStore(tmp_path, "TEST_V1")
    universe, market, signals = _inputs(); market["date"] = pd.Timestamp("2026-08-17")
    with pytest.raises(ValueError, match="Future-dated"):
        stage_a(store, config, "2026-08-14", universe, market, signals)
    assert not list((tmp_path / "signals").glob("*.parquet"))


def test_stage_a_orders_have_no_execution_price(tmp_path):
    _, store = _stage(tmp_path)
    orders = pd.read_parquet(store.root / "orders/primary_2026_08_14.parquet")
    assert "execution_price" not in orders and "observed_open" not in orders


def test_stage_b_consumes_frozen_order_hash(tmp_path):
    config, store = _stage(tmp_path)
    _, trades = stage_b(store, config, "primary", "2026-08-14", "2026-08-17",
                        pd.DataFrame({"ticker":["A"], "open":[101.]}), 30_000, {})
    assert trades.orders_sha256.notna().all()


def test_whole_share_execution(tmp_path):
    config, store = _stage(tmp_path)
    _, trades = stage_b(store, config, "primary", "2026-08-14", "2026-08-17",
                        pd.DataFrame({"ticker":["A"], "open":[101.]}), 30_000, {})
    assert (trades.shares % 1 == 0).all()


def test_account_persistence_uses_prior_positions(tmp_path):
    config, store = _stage(tmp_path)
    state, _ = stage_b(store, config, "primary", "2026-08-14", "2026-08-17",
                       pd.DataFrame({"ticker":["A"], "open":[100.]}), 30_000, {})
    assert state["positions"]["A"] == 299
    assert state["cash"] < 30_000


def test_no_leverage(tmp_path):
    config, store = _stage(tmp_path)
    state, _ = stage_b(store, config, "primary", "2026-08-14", "2026-08-17",
                       pd.DataFrame({"ticker":["A"], "open":[100.]}), 30_000, {})
    assert state["cash"] >= 0


def test_cost_accounting_once(tmp_path):
    config, store = _stage(tmp_path)
    _, trades = stage_b(store, config, "primary", "2026-08-14", "2026-08-17",
                        pd.DataFrame({"ticker":["A"], "open":[100.]}), 30_000, {})
    row = trades.query("status == 'EXECUTED'").iloc[0]
    assert row.estimated_cost == pytest.approx(row.trade_notional * 5 / 10_000)


def test_cost_parallelism_keeps_identical_trades(tmp_path):
    config, store = _stage(tmp_path)
    _, trades = stage_b(store, config, "primary", "2026-08-14", "2026-08-17",
                        pd.DataFrame({"ticker":["A"], "open":[100.]}), 30_000, {})
    parallel = parallel_cost_accounting(trades)
    assert parallel.groupby("cost_bps").shares.sum().nunique() == 1
    assert set(parallel.cost_bps) == {0,2,5,10,20}


def test_universe_snapshot_cannot_change(tmp_path):
    config, store = _stage(tmp_path); universe, _, _ = _inputs(); universe.loc[0,"sector"]="Changed"
    with pytest.raises(FileExistsError):
        store.write_frame("universe/universe_2026_08_14.parquet", universe, "UNIVERSE")


def test_sector_snapshot_is_frozen(tmp_path):
    _, store = _stage(tmp_path)
    frame = pd.read_parquet(store.root / "universe/universe_2026_08_14.parquet")
    assert frame.set_index("ticker").loc["A", "sector"] == "Tech"


def test_outcome_is_separate_from_signal(tmp_path):
    _, store = _stage(tmp_path); signal = store.root / "signals/signals_2026_08_14.parquet"
    before = signal.read_bytes()
    store.write_frame("outcomes/outcome_2026_08_14.parquet", pd.DataFrame({"ticker":["A"],"return_5d":[.01]}), "OUTCOME")
    assert signal.read_bytes() == before


def test_execution_is_idempotent(tmp_path):
    config, store = _stage(tmp_path); opens = pd.DataFrame({"ticker":["A"], "open":[100.]})
    stage_b(store, config, "primary", "2026-08-14", "2026-08-17", opens, 30_000, {})
    with pytest.raises(FileExistsError): stage_b(store, config, "primary", "2026-08-14", "2026-08-17", opens, 30_000, {})


def test_successful_transitions_write_audit(tmp_path):
    _, store = _stage(tmp_path)
    audit = pd.read_csv(store.audit_log)
    assert "SIGNAL_GENERATED" in set(audit.event_type)


def test_methodology_change_rejected_under_same_frozen_config(tmp_path):
    payload = _config(tmp_path).model_dump(); payload["signals"]["primary"] = "changed"
    with pytest.raises(ValueError): ProspectiveConfig.model_validate(payload)


def test_missing_open_is_explicitly_skipped(tmp_path):
    config, store = _stage(tmp_path)
    state, trades = stage_b(store, config, "primary", "2026-08-14", "2026-08-17",
                            pd.DataFrame({"ticker":[], "open":[]}), 30_000, {})
    assert trades.status.eq("SKIPPED_MISSING_OPEN").all() and state["cash"] == 30_000


def test_universe_rule_is_deterministic(tmp_path):
    config = _config(tmp_path); universe, _, _ = _inputs()
    result = eligible_universe(universe, config.universe).set_index("ticker")
    assert result.loc["A", "eligibility"] and not result.loc["B", "eligibility"]


def test_no_brokerage_code_or_imports():
    root = Path("src/quant_trading/prospective")
    text = "\n".join(path.read_text() for path in root.glob("*.py"))
    forbidden = ("schwab", "alpaca", "interactive_brokers", "submit_order", "oauth")
    assert not any(term in text.lower() for term in forbidden)


def test_benchmark_timing_requires_identical_periods():
    dates = pd.bdate_range("2026-08-17", periods=3)
    validate_benchmark_alignment(dates, dates)
    with pytest.raises(ValueError): validate_benchmark_alignment(dates, dates[1:])
