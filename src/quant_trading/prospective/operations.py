"""Operational status and fail-closed manual commands."""

import json
from pathlib import Path
from quant_trading.prospective.config import load_prospective_config
from quant_trading.prospective.storage import ArtifactStore


def initialize(config_path="config/prospective.yaml"):
    config = load_prospective_config(config_path)
    return config, ArtifactStore(config.storage_root, config.experiment_id)


def require_provider(config):
    if config.provider == "REQUIRED_SECURITY_MASTER_NOT_CONFIGURED":
        raise RuntimeError("No broad contemporaneous U.S. common-equity security master is configured")


def signal_command(config_path="config/prospective.yaml"):
    config, store = initialize(config_path)
    try:
        require_provider(config)
    except Exception as exc:
        store.audit("SIGNAL_GENERATED", "", "prospective-signal", "INVALID", errors=str(exc))
        raise


def unavailable_data_command(command, config_path="config/prospective.yaml"):
    config, store = initialize(config_path)
    message = f"{command} requires a configured prospective market-data provider"
    store.audit(command.upper().replace("-", "_"), "", command, "INVALID", errors=message)
    raise RuntimeError(message)


def verify_command(config_path="config/prospective.yaml"):
    config, store = initialize(config_path)
    result = store.verify()
    status = "SUCCESS" if result.empty or result.valid.all() else "INVALID"
    store.audit("INTEGRITY_VERIFIED", "", "prospective-verify", status,
                errors="" if status == "SUCCESS" else "Artifact hash mismatch")
    return result


def audit_command(config_path="config/prospective.yaml"):
    config, store = initialize(config_path)
    integrity = store.verify()
    return {"experiment_id":config.experiment_id, "hashes_valid":bool(integrity.empty or integrity.valid.all()),
            "artifact_count":len(integrity), "provider_configured":config.provider != "REQUIRED_SECURITY_MASTER_NOT_CONFIGURED"}


def write_status(config_path="config/prospective.yaml"):
    config, store = initialize(config_path)
    status = {"experiment_id":config.experiment_id, "status":"DATA_SOURCE_INSUFFICIENT",
              "prospective_observations":0, "provider":config.provider,
              "brokerage_connected":False}
    config.report_root.mkdir(parents=True, exist_ok=True)
    (config.report_root / "operational_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status
