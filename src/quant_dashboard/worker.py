"""Process boundary for allowlisted existing CLI functions; no arbitrary shell input."""
import argparse
import json
from pathlib import Path
import shutil
import traceback

from quant_dashboard.jobs import RunStore, now
from quant_dashboard.schemas import RunRequest
from quant_trading.prospective.storage import sha256_file


def execute(root: Path, identifier: str):
    store = RunStore(root)
    job = store.get(identifier)
    directory = store.run_dir(identifier)
    request = RunRequest.model_validate_json((directory / "request.json").read_text())
    store.update(identifier, status="running", started_at=now())
    print(json.dumps(dict(event="run_started", run_id=identifier, stage=job["stage"], timestamp=now())), flush=True)
    failure = None
    try:
        # Detect changed inputs rather than silently executing against a different dataset.
        for item in job["dataset"]:
            if sha256_file(root / item["identifier"]) != item["sha256"]:
                raise ValueError(f"Input checksum changed: {item['identifier']}")
        from quant_trading import cli
        functions = {"build-features": cli.build_features, "analyze-signals": cli.analyze_signals,
                     "expand-alpha-research": cli.expand_alpha_research,
                     "run-realistic-backtest": cli.run_realistic_backtest}
        if request.stage == "run-realistic-backtest":
            freeze = root / "reports/phase4/research_freeze.md"
            if freeze.exists():
                destination = directory / "outputs/phase4/research_freeze.md"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(freeze, destination)
        if request.stage == "bloomberg-import":
            cli.import_bloomberg(request.snapshot_date.isoformat(), root / "src/quant_trading/data/bloomberg", str(directory / "config.yaml"))
        else:
            functions[request.stage](str(directory / "config.yaml"))
        print(json.dumps(dict(event="run_succeeded", run_id=identifier, timestamp=now())), flush=True)
    except Exception as error:
        traceback.print_exc()
        failure = str(error)
        print(json.dumps(dict(event="run_failed", run_id=identifier, error=str(error), timestamp=now())), flush=True)
    finally:
        # Hash completed output and the exact config on both success and failure.
        hashes = {str(p.relative_to(directory)): sha256_file(p) for p in directory.rglob("*") if p.is_file() and p.name not in {"execution.log", "checksums.json"}}
        (directory / "checksums.json").write_text(json.dumps(hashes, indent=2))
        store.update(identifier, status="failed" if failure else "succeeded", completed_at=now(), error=failure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    execute(args.root.resolve(), args.run_id)
