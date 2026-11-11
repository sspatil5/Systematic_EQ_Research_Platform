export type Row = Record<string, string | number | boolean | null>
export type Period = 'FULL' | 'DEVELOPMENT' | 'CONFIRMATION'
export type Strategy = 'primary' | 'challenger' | 'raw_momentum_benchmark'
export interface Filters { run_id: string; strategy: Strategy; period: Period; start: string; end: string }
export interface Run {
  id: string; label: string; stage: string; status: 'historical' | 'queued' | 'running' | 'succeeded' | 'failed'
  created_at: string | null; started_at: string | null; completed_at: string | null
  git_commit: string | null; classification: string; error: string | null
  config_snapshot: Record<string, unknown> | null; dataset: Row[]; output_location: string | null
}
export interface Context {
  runs: Run[]; strategies: Strategy[]; periods: Period[]; dataset_start: string | null; dataset_end: string | null
  prospective: Record<string, unknown>
}
export interface Dataset {
  available: boolean; start: string | null; end: string | null; rows: number; securities: number
  coverage: number | null; freshness_days: number | null; sectors: string[]; source: string; warnings: string[]
}
export interface Backtest {
  available: boolean; run_id: string; strategy: string; period: string; metrics: Row; metrics_source: string | null
  initial_capital: number | null
  curve: Row[]; monthly: Row[]; annual: Row[]; configuration: Record<string, unknown>
  configuration_provenance: string; freeze_definition: string | null; warnings: string[]
}
export interface OverviewData {
  dataset: Dataset; backtest: Backtest; runs: Run[]; signals: Row[]; warnings: string[]
  latest_pipeline_status: string; latest_pipeline_at: string | null
}
export interface TablePage { items: Row[]; total: number; page: number; page_size: number; columns: string[]; note: string | null }
export interface SignalData {
  available: boolean; run_id: string; period: string; source: string; scorecard: Row[]
  daily_ic: Row[]; decay: Row[]; quantiles: Row[]; correlations: Row[]; note: string
}
export interface ImportStatus {
  status: string; snapshot_date: string | null; summary: Record<string, unknown>; errors: string[]
  history: Row[]; source_files: string[]
}
export interface Artifact {
  id: string; name: string; location: string; group: string; kind: string; size: number
  modified_at: string; recorded_sha256: string | null
}
export interface ArtifactPage { items: Artifact[]; total: number; page: number; page_size: number; groups: string[] }
export interface ArtifactPreview { artifact: Artifact; text: string | null; rows: Row[]; columns: string[]; total_rows: number | null; truncated: boolean }
export interface Integrity { id: string; actual_sha256: string; recorded_sha256: string | null; status: 'verified' | 'mismatch' | 'unrecorded' }
export interface Stage { id: string; label: string; description: string; prerequisites: string[]; available: boolean; reason: string | null }
export interface LogData { id: string; status: string; text: string; truncated: boolean }
