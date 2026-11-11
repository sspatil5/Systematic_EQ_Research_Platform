"""Public API contracts. Missing numbers are null, never invented or zero-filled."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Row = dict[str, Any]
Stage = Literal["build-features", "analyze-signals", "expand-alpha-research", "run-realistic-backtest", "bloomberg-import"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunRequest(StrictModel):
    stage: Stage
    snapshot_date: date | None = None

    @model_validator(mode="after")
    def import_date(self):
        if self.stage == "bloomberg-import" and self.snapshot_date is None:
            raise ValueError("A snapshot date is required for a Bloomberg import")
        if self.stage != "bloomberg-import" and self.snapshot_date is not None:
            raise ValueError("snapshot_date only applies to Bloomberg imports")
        return self


class Run(BaseModel):
    id: str
    label: str
    stage: str
    status: Literal["historical", "queued", "running", "succeeded", "failed"]
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    git_commit: str | None = None
    classification: str
    error: str | None = None
    config_snapshot: Row | None = None
    dataset: list[Row] = Field(default_factory=list)
    output_location: str | None = None


class Context(BaseModel):
    runs: list[Run]
    strategies: list[str]
    periods: list[str]
    dataset_start: str | None
    dataset_end: str | None
    prospective: Row


class TablePage(BaseModel):
    items: list[Row]
    total: int
    page: int
    page_size: int
    columns: list[str] = Field(default_factory=list)
    note: str | None = None


class Dataset(BaseModel):
    available: bool
    start: str | None = None
    end: str | None = None
    rows: int = 0
    securities: int = 0
    coverage: float | None = None
    freshness_days: int | None = None
    sectors: list[str] = Field(default_factory=list)
    source: str = "yfinance adjusted OHLCV · static development universe"
    warnings: list[str] = Field(default_factory=list)


class Backtest(BaseModel):
    available: bool
    run_id: str
    strategy: str
    period: str
    initial_capital: float | None = None
    metrics: Row = Field(default_factory=dict)
    metrics_source: str | None = None
    curve: list[Row] = Field(default_factory=list)
    monthly: list[Row] = Field(default_factory=list)
    annual: list[Row] = Field(default_factory=list)
    configuration: Row = Field(default_factory=dict)
    configuration_provenance: str
    freeze_definition: str | None = None
    warnings: list[str] = Field(default_factory=list)


class Signals(BaseModel):
    available: bool
    run_id: str
    period: str
    source: str
    scorecard: list[Row] = Field(default_factory=list)
    daily_ic: list[Row] = Field(default_factory=list)
    decay: list[Row] = Field(default_factory=list)
    quantiles: list[Row] = Field(default_factory=list)
    correlations: list[Row] = Field(default_factory=list)
    note: str


class Artifact(BaseModel):
    id: str
    name: str
    location: str
    group: str
    kind: str
    size: int
    modified_at: str
    recorded_sha256: str | None = None


class ArtifactPage(BaseModel):
    items: list[Artifact]
    total: int
    page: int
    page_size: int
    groups: list[str]


class ArtifactPreview(BaseModel):
    artifact: Artifact
    text: str | None = None
    rows: list[Row] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    total_rows: int | None = None
    truncated: bool = False


class Integrity(BaseModel):
    id: str
    actual_sha256: str
    recorded_sha256: str | None
    status: Literal["verified", "mismatch", "unrecorded"]


class ImportStatus(BaseModel):
    status: str
    snapshot_date: str | None = None
    summary: Row = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    history: list[Row] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)


class StageInfo(BaseModel):
    id: Stage
    label: str
    description: str
    prerequisites: list[str]
    available: bool
    reason: str | None = None


class Overview(BaseModel):
    dataset: Dataset
    backtest: Backtest
    runs: list[Run]
    signals: list[Row]
    warnings: list[str]
    latest_pipeline_status: str
    latest_pipeline_at: str | None


class LogResponse(BaseModel):
    id: str
    status: str
    text: str
    truncated: bool


class ConfigResponse(BaseModel):
    configuration: Row
    provenance: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
