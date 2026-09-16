"""Append-only audit and immutable, hashed artifact storage."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

MANIFEST_COLUMNS = ["experiment_id", "filename", "created_at", "sha256", "row_count", "maximum_market_date", "artifact_type"]
AUDIT_COLUMNS = ["timestamp", "experiment_id", "event_type", "signal_date", "command", "status", "files_created", "warnings", "errors"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ArtifactStore:
    def __init__(self, root: str | Path, experiment_id: str):
        self.root = Path(root); self.experiment_id = experiment_id
        self.root.mkdir(parents=True, exist_ok=True)
        for folder in ("universe", "market_data", "signals", "targets", "orders", "executions", "account", "benchmarks", "outcomes"):
            (self.root / folder).mkdir(exist_ok=True)
        self.manifest = self.root / "manifest.csv"
        self.audit_log = self.root / "audit_log.csv"
        if not self.manifest.exists():
            pd.DataFrame(columns=MANIFEST_COLUMNS).to_csv(self.manifest, index=False)
        if not self.audit_log.exists():
            pd.DataFrame(columns=AUDIT_COLUMNS).to_csv(self.audit_log, index=False)

    @staticmethod
    def _append_csv(path: Path, row: dict, columns: list[str]):
        pd.DataFrame([{key: row.get(key, "") for key in columns}]).to_csv(
            path, mode="a", header=False, index=False
        )

    def write_frame(self, relative: str, frame: pd.DataFrame, artifact_type: str,
                    maximum_market_date="") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"Immutable prospective artifact already exists: {path}")
        frame.to_parquet(path, index=False)
        self._append_csv(self.manifest, {
            "experiment_id": self.experiment_id, "filename": str(path.relative_to(self.root)),
            "created_at": datetime.now(timezone.utc).isoformat(), "sha256": sha256_file(path),
            "row_count": len(frame), "maximum_market_date": maximum_market_date,
            "artifact_type": artifact_type,
        }, MANIFEST_COLUMNS)
        return path

    def write_json(self, relative: str, payload: dict, artifact_type: str) -> Path:
        path = self.root / relative
        if path.exists():
            raise FileExistsError(f"Immutable prospective artifact already exists: {path}")
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self._append_csv(self.manifest, {
            "experiment_id": self.experiment_id, "filename": str(path.relative_to(self.root)),
            "created_at": datetime.now(timezone.utc).isoformat(), "sha256": sha256_file(path),
            "row_count": 1, "maximum_market_date": "", "artifact_type": artifact_type,
        }, MANIFEST_COLUMNS)
        return path

    def register_file(self, path: str | Path, artifact_type: str, row_count: int,
                      snapshot_date: str = "") -> None:
        """Register an existing immutable source without copying or modifying it."""
        path = Path(path).resolve()
        filename = str(path.relative_to(self.root.resolve().parent.parent)) if path.is_relative_to(
            self.root.resolve().parent.parent
        ) else str(path)
        manifest = pd.read_csv(self.manifest)
        existing = manifest.loc[manifest["filename"].eq(filename)]
        digest = sha256_file(path)
        if not existing.empty:
            if not existing.iloc[-1]["sha256"] == digest:
                raise ValueError(f"Registered source hash changed: {path}")
            return
        self._append_csv(self.manifest, {
            "experiment_id": self.experiment_id, "filename": filename,
            "created_at": datetime.now(timezone.utc).isoformat(), "sha256": digest,
            "row_count": row_count, "maximum_market_date": snapshot_date,
            "artifact_type": artifact_type,
        }, MANIFEST_COLUMNS)

    def audit(self, event_type, signal_date, command, status, files=(), warnings="", errors=""):
        self._append_csv(self.audit_log, {
            "timestamp": datetime.now(timezone.utc).isoformat(), "experiment_id": self.experiment_id,
            "event_type": event_type, "signal_date": signal_date, "command": command,
            "status": status, "files_created": ";".join(map(str, files)),
            "warnings": warnings, "errors": errors,
        }, AUDIT_COLUMNS)

    def verify(self) -> pd.DataFrame:
        manifest = pd.read_csv(self.manifest)
        rows = []
        for row in manifest.itertuples(index=False):
            candidate = Path(row.filename)
            path = candidate if candidate.is_absolute() else (
                self.root.parent.parent / candidate if str(candidate).startswith("src/")
                else self.root / candidate
            )
            actual = sha256_file(path) if path.exists() else "MISSING"
            rows.append({"filename": row.filename, "expected_sha256": row.sha256,
                         "actual_sha256": actual, "valid": actual == row.sha256})
        return pd.DataFrame(rows, columns=["filename", "expected_sha256", "actual_sha256", "valid"])
