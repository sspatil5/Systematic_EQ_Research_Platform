"""Single-worker local jobs with persistent metadata and isolated output directories."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import uuid

import yaml

from quant_dashboard.schemas import RunRequest
from quant_trading.prospective.storage import sha256_file


def now():
    return datetime.now(timezone.utc).isoformat()


class ConflictError(Exception):
    pass


class RunStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.storage = self.root / "data/dashboard"
        self.runs_root = self.storage / "runs"
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.database = self.storage / "runs.sqlite3"
        with self.connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, label TEXT, stage TEXT, status TEXT,
                created_at TEXT, started_at TEXT, completed_at TEXT, git_commit TEXT,
                classification TEXT, error TEXT, config_snapshot TEXT, dataset TEXT,
                output_location TEXT, owner_pid INTEGER)""")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON runs ((1)) WHERE status IN ('queued', 'running')")

    def connect(self):
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def run_dir(self, identifier):
        try:
            uuid.UUID(identifier)
        except (ValueError, TypeError):
            raise KeyError("Unknown run") from None
        return self.runs_root / identifier

    @staticmethod
    def decode(row):
        result = dict(row)
        result.pop("owner_pid", None)
        for key in ("config_snapshot", "dataset"):
            result[key] = json.loads(result[key]) if result[key] else None
        return result

    def get(self, identifier):
        self.run_dir(identifier)
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (identifier,)).fetchone()
        if row is None:
            raise KeyError("Unknown run")
        return self.decode(row)

    def list(self):
        with self.connect() as connection:
            return [self.decode(row) for row in connection.execute("SELECT * FROM runs ORDER BY created_at DESC")]

    def update(self, identifier, **values):
        allowed = {"status", "started_at", "completed_at", "error"}
        if not values or set(values) - allowed:
            raise ValueError("Unsupported metadata update")
        with self.connect() as connection:
            connection.execute(f"UPDATE runs SET {', '.join(k+' = ?' for k in values)} WHERE id = ?", [*values.values(), identifier])

    def recover(self):
        with self.connect() as connection:
            for row in connection.execute("SELECT id, owner_pid FROM runs WHERE status IN ('queued','running')").fetchall():
                try:
                    os.kill(row["owner_pid"], 0)
                except ProcessLookupError:
                    connection.execute("UPDATE runs SET status='failed', completed_at=?, error=? WHERE id=?",
                                       (now(), "Dashboard process stopped before completion; create a new run to retry.", row["id"]))


class JobManager:
    def __init__(self, store: RunStore):
        self.store = store
        self.root = store.root
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quant-dashboard")
        self.processes = {}
        self.lock = threading.Lock()
        self.closed = False

    def stages(self):
        research_dependencies = all(importlib.util.find_spec(name) is not None for name in ("matplotlib", "scipy", "statsmodels"))
        configuration = (self.root / "config/research.yaml").is_file()
        try:
            config = yaml.safe_load((self.root / "config/research.yaml").read_text()) if configuration else {}
            panel = (self.root / config.get("data", {}).get("processed_path", "data/processed/daily_panel.parquet")).is_file()
            features = (self.root / config.get("features", {}).get("output_path", "data/processed/features.parquet")).is_file()
        except (ValueError, TypeError, AttributeError, yaml.YAMLError):
            configuration, panel, features = False, False, False
        sources = bool(list((self.root / "src/quant_trading/data/bloomberg").glob("*.xlsx")))
        sources = sources and (self.root / "config/prospective.yaml").is_file()
        return [dict(id=stage, label=label, description=description, prerequisites=prerequisites,
                     available=available and configuration and research_dependencies,
                     reason="Required input artifacts or configuration are missing." if not available or not configuration else
                     "Install the Python research optional dependencies to run this stage (the existing CLI imports research modules)." if not research_dependencies else None)
                for stage, label, description, prerequisites, available in [
                    ("build-features", "Build features", "Generate the existing feature and forward-target dataset in a new run directory.", ["Canonical daily panel"], panel),
                    ("analyze-signals", "Analyze signals", "Run the existing Phase 3 statistical diagnostics and figures.", ["Saved feature dataset"], features),
                    ("expand-alpha-research", "Alpha research", "Execute the existing post-selection development / confirmation design.", ["Canonical daily panel", "Saved feature dataset"], panel and features),
                    ("run-realistic-backtest", "Realistic backtest", "Run the full frozen Phase 4 design, including 100 randomization seeds. This can take hours.", ["Canonical daily panel", "Saved feature dataset", "Research optional dependencies"], panel and features),
                    ("bloomberg-import", "Validate Bloomberg import", "Import the repository XLSX source set into an isolated run. All critical validation remains enforced.", ["Repository Bloomberg XLSX files", "Source snapshot date"], sources),
                ]]

    def submit(self, request: RunRequest):
        info = next(item for item in self.stages() if item["id"] == request.stage)
        if not info["available"]:
            raise ValueError(info["reason"])
        # Validate dependencies and strict research config before accepting a costly run.
        from quant_trading.utils.config import ResearchConfig
        config = yaml.safe_load((self.root / "config/research.yaml").read_text())
        ResearchConfig.model_validate(config)
        identifier = str(uuid.uuid4())
        directory = self.store.run_dir(identifier)
        original = yaml.safe_load((self.root / "config/prospective.yaml").read_text()) if request.stage == "bloomberg-import" else config
        if request.stage == "bloomberg-import":
            original["storage_root"] = str(directory / "prospective")
            original["report_root"] = str(directory / "outputs/phase5")
            inputs = sorted((self.root / "src/quant_trading/data/bloomberg").glob("*.xlsx"))
        else:
            original["data"]["processed_path"] = str(self.root / config["data"]["processed_path"])
            original["data"]["cache_dir"] = str(directory / "cache")
            original["features"]["output_path"] = str(directory / "outputs/features.parquet") if request.stage == "build-features" else str(self.root / config["features"]["output_path"])
            for key, phase in [("signal_research", "phase3"), ("alpha_research", "phase3_5"), ("backtest", "phase4")]:
                original[key]["output_dir"] = str(directory / "outputs" / phase)
            inputs = [self.root / config["data"]["processed_path"]]
            if request.stage != "build-features":
                inputs.append(self.root / config["features"]["output_path"])
        datasets = [dict(identifier=str(p.relative_to(self.root)), sha256=sha256_file(p), size=p.stat().st_size) for p in inputs if p.is_file()]
        git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True, text=True)
        commit = git.stdout.strip() if git.returncode == 0 else None
        payload = dict(id=identifier, label=info["label"], stage=request.stage, status="queued", created_at=now(),
                       git_commit=commit, classification="New exploratory execution of existing definitions; not new preregistration or prospective performance.",
                       config_snapshot=json.dumps(original), dataset=json.dumps(datasets),
                       output_location=str(directory.relative_to(self.root)), owner_pid=os.getpid())
        with self.lock:
            if self.closed:
                raise ConflictError("Job service is shutting down")
            with self.store.connect() as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(f"INSERT INTO runs ({','.join(payload)}) VALUES ({','.join('?' for _ in payload)})", list(payload.values()))
                except sqlite3.IntegrityError:
                    raise ConflictError("A pipeline job is already queued or running. Wait for it to finish before launching another.") from None
            directory.mkdir()
            (directory / "outputs").mkdir()
            (directory / "config.yaml").write_text(yaml.safe_dump(original, sort_keys=False))
            (directory / "request.json").write_text(request.model_dump_json())
            (directory / "input_manifest.json").write_text(json.dumps(datasets, indent=2))
            self.executor.submit(self.execute, identifier)
        return self.store.get(identifier)

    def execute(self, identifier):
        log = self.store.run_dir(identifier) / "execution.log"
        try:
            with log.open("w") as handle:
                with self.lock:
                    if self.closed:
                        raise RuntimeError("Dashboard stopped before execution")
                    env = os.environ.copy()
                    env["PYTHONPATH"] = str(self.root / "src") + os.pathsep + env.get("PYTHONPATH", "")
                    env["MPLBACKEND"] = "Agg"
                    process = subprocess.Popen([sys.executable, "-u", "-m", "quant_dashboard.worker", "--root", str(self.root), "--run-id", identifier],
                                               cwd=self.root, stdout=handle, stderr=subprocess.STDOUT, env=env)
                    self.processes[identifier] = process
                process.wait()
            if self.store.get(identifier)["status"] in ("running", "queued"):
                self.store.update(identifier, status="failed", completed_at=now(), error=f"Worker exited before recording completion (exit {process.returncode}).")
        except Exception as error:
            self.store.update(identifier, status="failed", completed_at=now(), error=str(error))
        finally:
            with self.lock:
                self.processes.pop(identifier, None)

    def close(self):
        with self.lock:
            self.closed = True
            processes = list(self.processes.values())
        for process in processes:
            if process.poll() is None:
                process.terminate()
        self.executor.shutdown(wait=True)
