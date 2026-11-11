"""FastAPI integration for local-only quantitative research workflows."""
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import time
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from quant_dashboard.jobs import ConflictError, JobManager, RunStore
from quant_dashboard.repository import Filters, Repository, records
from quant_dashboard.schemas import (ArtifactPage, ArtifactPreview, Backtest, ConfigResponse, Context,
                                     Dataset, ErrorResponse, ImportStatus, Integrity, LogResponse,
                                     Overview, Run, RunRequest, Signals, StageInfo, TablePage)

logger = logging.getLogger("quant_dashboard")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def create_app(root: Path | None = None, enable_jobs=True):
    root = (root or Path(os.environ.get("QUANT_RESEARCH_ROOT", Path(__file__).resolve().parents[2]))).resolve()
    store = RunStore(root)
    repository = Repository(root, store)
    manager = JobManager(store)

    @asynccontextmanager
    async def lifespan(_):
        store.recover()
        yield
        manager.close()

    app = FastAPI(title="Quantitative Research Dashboard", version="1.0.0", lifespan=lifespan,
                  responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
                             409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
    app.state.repository, app.state.jobs, app.state.store = repository, manager, store

    @app.middleware("http")
    async def local_actions(request: Request, call_next):
        # Reject browser cross-origin mutations. Bind the server to loopback as documented.
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin not in {"http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8000", "http://localhost:8000"}:
                return JSONResponse(status_code=403, content={"error": "forbidden_origin", "detail": "Pipeline actions are available only from the local dashboard."})
        start = time.monotonic()
        response = await call_next(request)
        logger.info(json.dumps(dict(event="request", method=request.method, path=request.url.path,
                                    status=response.status_code, duration_ms=round((time.monotonic()-start)*1000, 1))))
        return response

    @app.exception_handler(KeyError)
    async def missing(_, error):
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": str(error).strip("'")})

    @app.exception_handler(ValueError)
    async def invalid(_, error):
        return JSONResponse(status_code=400, content={"error": "invalid_request", "detail": str(error).replace(str(root), "[repository]")})

    @app.exception_handler(RequestValidationError)
    async def validation(_, error):
        return JSONResponse(status_code=422, content={"error": "validation_error", "detail": "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())})

    @app.exception_handler(HTTPException)
    async def http_error(_, error):
        return JSONResponse(status_code=error.status_code, content={"error": "request_rejected", "detail": str(error.detail)})

    @app.exception_handler(Exception)
    async def failed(_, error):
        logger.exception("Artifact request failed", exc_info=error)
        return JSONResponse(status_code=500, content={"error": "artifact_error", "detail": "Unable to read a research artifact. Check the API log for the file and validation error."})

    def public(run):
        return {**run, "config_snapshot": repository.public_config(run.get("config_snapshot"))}

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "local_research", "live_execution": False}

    @app.get("/api/context", response_model=Context)
    def context():
        data = repository.dataset(Filters())
        prospective_path = root / "reports/phase5/operational_status.json"
        prospective = json.loads(prospective_path.read_text()) if prospective_path.exists() else {"status": "unavailable"}
        legacy = Run(id="historical", label="Repository artifacts", stage="archive", status="historical", classification="Existing historical artifacts; not a single recorded pipeline execution.")
        return dict(runs=[legacy, *[public(r) for r in store.list()]], strategies=["primary", "challenger", "raw_momentum_benchmark"],
                    periods=["FULL", "DEVELOPMENT", "CONFIRMATION"], dataset_start=data.start, dataset_end=data.end,
                    prospective=prospective)

    @app.get("/api/dataset", response_model=Dataset)
    def dataset(filters: Annotated[Filters, Query()]):
        return repository.dataset(filters)

    @app.get("/api/overview", response_model=Overview)
    def overview(filters: Annotated[Filters, Query()]):
        data = repository.dataset(filters)
        imports = repository.import_status()
        warnings = list(data.warnings)
        if imports["status"] == "failed":
            warnings.append("Bloomberg security-master import failed critical schema validation. No normalized universe was authorized.")
        signals = repository.signals(filters)
        jobs = [public(r) for r in store.list()]
        history = imports["history"]
        latest = jobs[0] if jobs else None
        return dict(dataset=data, backtest=repository.backtest(filters), runs=[*jobs[:4], *repository.historical_runs()],
                    signals=sorted(signals["scorecard"], key=lambda row: abs(row.get("mean_rank_ic") or 0), reverse=True)[:5],
                    warnings=warnings, latest_pipeline_status=latest["status"] if latest else (history[-1].get("status", "unrecorded") if history else "unrecorded"),
                    latest_pipeline_at=latest["created_at"] if latest else (history[-1].get("timestamp") if history else None))

    @app.get("/api/universe", response_model=TablePage)
    def universe(run_id: str = "historical", period: str = "FULL", start: str | None = None, end: str | None = None,
                 search: str = Query("", max_length=100), sector: str = Query("", max_length=100),
                 minimum_liquidity: float = Query(0, ge=0), eligible_only: bool = False,
                 sort: str = "ticker", descending: bool = False, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200)):
        filters = Filters(run_id=run_id, period=period, start=start, end=end)
        return repository.universe(filters, search, sector, minimum_liquidity, eligible_only, sort, descending, page, page_size)

    @app.get("/api/backtest", response_model=Backtest)
    def backtest(filters: Annotated[Filters, Query()]):
        return repository.backtest(filters)

    @app.get("/api/signals", response_model=Signals)
    def signals(run_id: str = "historical", period: str = "FULL", start: str | None = None, end: str | None = None,
                signal: str | None = Query(None, max_length=120)):
        return repository.signals(Filters(run_id=run_id, period=period, start=start, end=end), signal)

    @app.get("/api/bloomberg", response_model=ImportStatus)
    def bloomberg():
        return repository.import_status()

    @app.get("/api/artifacts", response_model=ArtifactPage)
    def artifacts(run_id: str = "historical", search: str = Query("", max_length=100), group: str = "", kind: str = "",
                  sort: str = "modified_at", descending: bool = True,
                  page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200)):
        index = repository.artifact_index(run_id)
        items = [meta for _, meta in index.values()]
        groups = sorted({meta.group for meta in items})
        if sort not in {"name", "group", "kind", "size", "modified_at", "recorded_sha256"}:
            raise ValueError("Unsupported artifact sort column")
        items = sorted([meta for meta in items if (not search or search.lower() in meta.location.lower()) and (not group or meta.group == group) and (not kind or meta.kind == kind)], key=lambda meta: getattr(meta, sort) or "", reverse=descending)
        return dict(items=items[(page-1)*page_size:page*page_size], total=len(items), page=page, page_size=page_size, groups=groups)

    @app.get("/api/artifacts/{identifier}/preview", response_model=ArtifactPreview)
    def preview(identifier: str, run_id: str = "historical"):
        return repository.preview(identifier, run_id)

    @app.get("/api/artifacts/{identifier}/download")
    def download(identifier: str, run_id: str = "historical"):
        path, meta = repository.artifact(identifier, run_id)
        return FileResponse(path, filename=meta.name, media_type="application/octet-stream")

    @app.get("/api/artifacts/{identifier}/image")
    def image(identifier: str, run_id: str = "historical"):
        path, _ = repository.artifact(identifier, run_id)
        if path.suffix != ".png":
            raise HTTPException(status_code=400, detail="Inline previews support PNG only")
        return FileResponse(path, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"})

    @app.get("/api/artifacts/{identifier}/integrity", response_model=Integrity)
    def integrity(identifier: str, run_id: str = "historical"):
        return repository.verify(identifier, run_id)

    @app.get("/api/runs", response_model=list[Run])
    def runs():
        return [*[public(r) for r in store.list()], *repository.historical_runs()]

    @app.get("/api/stages", response_model=list[StageInfo])
    def stages():
        result = manager.stages()
        if not enable_jobs:
            for item in result:
                item.update(available=False, reason="Pipeline execution disabled by this API instance.")
        return result

    @app.post("/api/runs", response_model=Run, status_code=202)
    def launch(request: RunRequest):
        if not enable_jobs:
            raise HTTPException(status_code=403, detail="Pipeline execution disabled")
        try:
            return public(manager.submit(request))
        except ConflictError as error:
            return JSONResponse(status_code=409, content={"error": "job_conflict", "detail": str(error)})

    @app.get("/api/runs/{identifier}", response_model=Run)
    def run(identifier: str):
        return public(store.get(identifier))

    @app.get("/api/runs/{identifier}/logs", response_model=LogResponse)
    def logs(identifier: str):
        job = store.get(identifier)
        path = store.run_dir(identifier) / "execution.log"
        size = path.stat().st_size if path.exists() else 0
        if size:
            with path.open("rb") as handle:
                handle.seek(max(0, size-100000))
                text = handle.read().decode("utf-8", errors="replace").replace(str(root), "[repository]")
        else:
            text = "Waiting for the worker…"
        return dict(id=identifier, status=job["status"], text=text, truncated=size > 100000)

    @app.get("/api/config", response_model=ConfigResponse)
    def config(run_id: str = "historical"):
        return dict(configuration=repository.public_config(repository.config(run_id)),
                    provenance="Current reference YAML; original historical machine snapshot not available." if run_id == "historical" else "Immutable per-run snapshot.")

    # Optional production frontend: build once, then serve both layers on loopback:8000.
    dist = root / "dashboard/dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
    return app


app = create_app()
