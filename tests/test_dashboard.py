"""Integration contracts for the dashboard; synthetic fixtures never enter research artifacts."""
from pathlib import Path
import hashlib
import json
import time

import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
import yaml

from quant_dashboard.app import create_app
from quant_dashboard.jobs import ConflictError, JobManager, RunStore
from quant_dashboard.schemas import RunRequest
from quant_trading.utils.config import ResearchConfig


@pytest.fixture
def repository_root(tmp_path):
    for name in ("config", "data/processed", "reports/phase3", "reports/phase4", "reports/phase5"):
        (tmp_path / name).mkdir(parents=True)
    config = ResearchConfig.model_validate({"data": {"start": "2020-01-01"}}).model_dump(mode="json")
    (tmp_path / "config/research.yaml").write_text(yaml.safe_dump(config))
    (tmp_path / "config/prospective.yaml").write_text("experiment_id: TEST_ONLY\n")
    dates = pd.bdate_range("2020-01-01", periods=300)
    index = pd.MultiIndex.from_product([dates, ["AAPL", "SPY"]], names=["date", "ticker"])
    panel = pd.DataFrame(index=index)
    close = 100 + np.repeat(np.arange(len(dates))*0.1, 2)
    panel["open"] = close
    panel["high"] = close + 1
    panel["low"] = close - 1
    panel["close"] = close
    panel["volume"] = 1000000
    panel["possible_extreme_return"] = False
    panel.to_parquet(tmp_path / "data/processed/daily_panel.parquet")
    pd.DataFrame({"avg_dollar_volume_20": 100000000.0}, index=index).to_parquet(tmp_path / "data/processed/features.parquet")
    pd.DataFrame({"ticker": ["AAPL", "SPY"], "sector": ["Technology", "ETF"]}).to_csv(tmp_path / "data/processed/sector_mapping.csv", index=False)
    daily = pd.DataFrame({"net_return": [0.01, -0.02, 0.03], "equity": [1010., 989.8, 1019.494], "daily_cost": [1.,2.,3.], "turnover": [.1,.2,.3], "cash_weight": [.01,.02,.01]}, index=pd.DatetimeIndex(["2020-01-02", "2020-01-03", "2020-01-06"], name="date"))
    daily.to_parquet(tmp_path / "reports/phase4/primary_daily.parquet")
    pd.DataFrame({"date": daily.index, "spy": [.005,-.01,.01], "equal_weight": [.002,-.01,.02]}).to_csv(tmp_path / "reports/phase4/benchmarks.csv",index=False)
    summary = dict(start="2020-01-02", end="2020-01-06", observations=3, total_return=.019494,
                   cagr=.123456789, annualized_volatility=.22, zero_rate_sharpe=.987654321,
                   max_drawdown=-.02, estimated_costs=6., annual_turnover=.5, sample="FULL",
                   ending_equity=1019.494, spy_cagr=.06, equal_weight_cagr=.07, strategy="primary")
    pd.DataFrame([summary]).to_csv(tmp_path / "reports/phase4/strategy_summary.csv",index=False)
    pd.DataFrame([dict(signal="ret_1d",mean_rank_ic=-.01,hac_t_stat=-2.3,raw_p_value=.02,fdr_q_value=.04,classification="WEAK / INCONCLUSIVE",turnover=np.nan)]).to_csv(tmp_path / "reports/phase3/signal_scorecard.csv",index=False)
    (tmp_path / "reports/phase4/research_freeze.md").write_text("# Fixture freeze\nImmutable source")
    return tmp_path


@pytest.fixture
def client(repository_root):
    with TestClient(create_app(repository_root, enable_jobs=False)) as client:
        yield client


def test_stored_metrics_remain_exact_and_missing_values_are_null(client):
    result = client.get("/api/backtest").json()
    assert result["available"]
    assert result["metrics"]["cagr"] == .123456789
    assert result["metrics"]["zero_rate_sharpe"] == .987654321
    assert result["curve"][-1]["portfolio"] == pytest.approx(1019.494)
    assert result["curve"][0]["rolling_sharpe"] is None
    assert result["curve"][1]["drawdown"] == pytest.approx(-.02)
    assert result["configuration_provenance"].startswith("Current reference")
    signal = client.get("/api/signals").json()["scorecard"][0]
    assert signal["turnover"] is None


def test_float_serialization_retains_full_precision():
    from quant_dashboard.repository import records
    value = .2326852807076712
    assert records(pd.DataFrame({"metric": [value, np.inf, np.nan]})) == [
        {"metric": value}, {"metric": None}, {"metric": None}]


def test_custom_dates_use_existing_metrics_and_saved_returns(client):
    response = client.get("/api/backtest?start=2020-01-03&end=2020-01-06")
    assert response.status_code == 200
    result = response.json()
    assert result["metrics"]["observations"] == 2
    assert result["metrics"]["estimated_costs"] == 5
    assert result["metrics"]["total_return"] == pytest.approx(.0094)
    assert len(result["curve"]) == 2
    assert "performance_metrics" in result["metrics_source"]


def test_universe_filters_pagination_and_no_inferred_identifiers(client):
    result = client.get("/api/universe?search=aa&sector=Technology&page_size=1").json()
    assert result["total"] == 1
    assert result["items"][0]["ticker"] == "AAPL"
    assert result["items"][0]["security_id"] is None
    assert result["items"][0]["exchange"] is None
    assert client.get("/api/universe?minimum_liquidity=200000000").json()["total"] == 0
    assert client.get("/api/universe?page=2&page_size=1").json()["items"][0]["ticker"] == "SPY"
    assert client.get("/api/universe?sort=arbitrary").status_code == 400


def test_schemas_invalid_dates_and_unavailable_contexts(client):
    for path in ["/api/context", "/api/overview", "/api/dataset", "/api/signals", "/api/stages", "/api/bloomberg", "/api/runs", "/api/config"]:
        assert client.get(path).status_code == 200, path
    assert client.get("/api/backtest?period=invalid").status_code == 422
    assert client.get("/api/backtest?start=2025-01-02&end=2020-01-01").status_code == 422
    assert client.get("/api/backtest?start=oops").status_code == 422
    assert not client.get("/api/backtest?strategy=challenger").json()["available"]
    assert not client.get("/api/backtest?start=2030-01-01").json()["available"]
    assert client.get("/api/signals?period=CONFIRMATION").json()["scorecard"] == []
    assert client.get("/api/backtest?run_id=../../").status_code == 404


def test_missing_dataset_and_reports_are_explicit(tmp_path):
    with TestClient(create_app(tmp_path, enable_jobs=False)) as client:
        assert client.get("/api/dataset").json()["available"] is False
        assert client.get("/api/overview").status_code == 200
        assert client.get("/api/artifacts").json()["total"] == 0


def test_safe_artifact_preview_download_integrity_and_symlinks(client, repository_root, tmp_path):
    secret = repository_root / "secret.txt"
    secret.write_text("not an artifact")
    (repository_root / "reports/phase4/escape.md").symlink_to(secret)
    items = client.get("/api/artifacts?page_size=200").json()["items"]
    assert all(item["name"] != "escape.md" for item in items)
    artifact = next(item for item in items if item["name"] == "research_freeze.md")
    identifier = artifact["id"]
    assert client.get(f"/api/artifacts/{identifier}/preview").json()["text"] == "# Fixture freeze\nImmutable source"
    assert client.get(f"/api/artifacts/{identifier}/download").content == b"# Fixture freeze\nImmutable source"
    digest = client.get(f"/api/artifacts/{identifier}/integrity").json()
    assert digest["status"] == "unrecorded"
    assert digest["actual_sha256"] == hashlib.sha256(b"# Fixture freeze\nImmutable source").hexdigest()
    assert client.get("/api/artifacts/not-a-file/download").status_code == 404
    assert client.get("/api/artifacts/%2E%2E%2F%2E%2E%2Fsecret.txt/download").status_code == 404


def test_mutations_have_fixed_schema_and_reject_cross_origin(client):
    assert client.post("/api/runs",json={"stage":"rm -rf /"}).status_code == 422
    assert client.post("/api/runs",json={"stage":"build-features", "command":"anything"}).status_code == 422
    assert client.post("/api/runs",json={"stage":"bloomberg-import"}).status_code == 422
    assert client.post("/api/runs",json={"stage":"build-features"},headers={"Origin":"https://untrusted.example"}).status_code == 403
    assert client.post("/api/runs",json={"stage":"build-features"}).status_code == 403


def test_background_job_preserves_inputs_metadata_and_checksums(repository_root):
    panel_path = repository_root / "data/processed/daily_panel.parquet"
    feature_path = repository_root / "data/processed/features.parquet"
    original = hashlib.sha256(panel_path.read_bytes()).hexdigest()
    original_features = hashlib.sha256(feature_path.read_bytes()).hexdigest()
    with TestClient(create_app(repository_root)) as client:
        response = client.post("/api/runs",json={"stage":"build-features"})
        assert response.status_code == 202, response.text
        job = response.json()
        assert job["dataset"][0]["sha256"] == original
        identifier = job["id"]
        for _ in range(200):
            job = client.get(f"/api/runs/{identifier}").json()
            if job["status"] in ("succeeded","failed"):
                break
            time.sleep(.05)
        assert job["status"] == "succeeded", client.get(f"/api/runs/{identifier}/logs").text
        assert job["started_at"] and job["completed_at"]
        assert job["config_snapshot"]["features"]["output_path"].startswith(f"data/dashboard/runs/{identifier}")
        assert (repository_root / job["output_location"] / "config.yaml").exists()
        assert hashlib.sha256(panel_path.read_bytes()).hexdigest() == original
        assert hashlib.sha256(feature_path.read_bytes()).hexdigest() == original_features
        items = client.get(f"/api/artifacts?run_id={identifier}").json()["items"]
        output = next(item for item in items if item["name"] == "features.parquet")
        assert client.get(f"/api/artifacts/{output['id']}/integrity?run_id={identifier}").json()["status"] == "verified"
        assert "run_succeeded" in client.get(f"/api/runs/{identifier}/logs").json()["text"]


def test_conflicting_jobs_are_rejected_across_managers(repository_root, monkeypatch):
    manager = JobManager(RunStore(repository_root))
    other = JobManager(RunStore(repository_root))
    monkeypatch.setattr(manager.executor, "submit", lambda *args: None)
    try:
        job = manager.submit(RunRequest(stage="build-features"))
        with pytest.raises(ConflictError):
            other.submit(RunRequest(stage="build-features"))
        assert manager.store.get(job["id"])["status"] == "queued"
    finally:
        manager.close()
        other.close()


def test_recorded_hash_verifies_and_detects_changes(client, repository_root):
    source = repository_root / "src/quant_trading/data/bloomberg/master.xlsx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fixture source")
    manifest = repository_root / "data/prospective/manifest.csv"
    manifest.parent.mkdir(parents=True)
    pd.DataFrame([dict(filename="src/quant_trading/data/bloomberg/master.xlsx",sha256=hashlib.sha256(source.read_bytes()).hexdigest())]).to_csv(manifest,index=False)
    artifact = next(item for item in client.get("/api/artifacts?kind=xlsx").json()["items"] if item["name"] == "master.xlsx")
    assert client.get(f"/api/artifacts/{artifact['id']}/integrity").json()["status"] == "verified"
    source.write_bytes(b"modified source")
    assert client.get(f"/api/artifacts/{artifact['id']}/integrity").json()["status"] == "mismatch"


def test_worker_failure_records_traceback_without_overwriting(repository_root, monkeypatch):
    manager = JobManager(RunStore(repository_root))
    monkeypatch.setattr(manager.executor, "submit", lambda *args: None)
    job = manager.submit(RunRequest(stage="build-features"))
    # Changing an input after queuing is rejected before research code runs.
    with (repository_root / "data/processed/daily_panel.parquet").open("ab") as handle:
        handle.write(b"changed")
    from quant_dashboard.worker import execute
    execute(repository_root,job["id"])
    result = manager.store.get(job["id"])
    assert result["status"] == "failed"
    assert "Input checksum changed" in result["error"]
    assert (manager.store.run_dir(job["id"]) / "checksums.json").exists()
    manager.close()
