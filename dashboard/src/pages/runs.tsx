import { useEffect, useState } from 'react'
import { Check, CirclePlay, Clock3, Code2, GitBranch, LoaderCircle, TerminalSquare } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { DataTable } from '../components/data-table'
import { Badge, Failure, Loading, Note, PageHeader, Status } from '../components/shared'
import { api, label, query, timestamp, useApi } from '../lib'
import type { Filters, LogData, Run, Stage } from '../types'

function RunDetail({ run }: { run: Run }) {
  const result = useApi<LogData>(run.status === 'historical' ? null : `/runs/${run.id}/logs`, ['running','queued'].includes(run.status) ? 2000 : 0)
  return <Card><CardHeader title="Execution detail" subtitle={run.id} action={<Status value={run.status} />} />
    <div className="run-meta"><div><span>Created</span><strong>{timestamp(run.created_at)}</strong></div><div><span>Started</span><strong>{timestamp(run.started_at)}</strong></div><div><span>Completed</span><strong>{timestamp(run.completed_at)}</strong></div><div><span>Git revision</span><strong className="mono">{run.git_commit?.slice(0,12) || 'Not recorded'}</strong></div></div>
    <Note>{run.classification} Output: {run.output_location || 'Not recorded'}.</Note>
    {run.error && <div className="inline-error" role="alert">{run.error}</div>}
    {run.status !== 'historical' && <><div className="log-heading"><TerminalSquare size={15} />Worker output {['running','queued'].includes(run.status) && <Badge tone="blue">Polling every 2s</Badge>}</div>{result.error ? <Note tone="amber">{result.error}</Note> : <pre className="execution-log">{result.data?.text || 'Loading worker output…'}</pre>}</>}
    {run.config_snapshot && <details className="freeze-details"><summary>Immutable configuration snapshot</summary><pre>{JSON.stringify(run.config_snapshot,null,2)}</pre></details>}
    {!!run.dataset.length && <details className="freeze-details"><summary>Input dataset versions & SHA-256</summary><pre>{JSON.stringify(run.dataset,null,2)}</pre></details>}
  </Card>
}
export function Runs({ filters, onLaunched }: { filters: Filters; onLaunched: () => void }) {
  const stages = useApi<Stage[]>('/stages')
  const runs = useApi<Run[]>('/runs', 3000)
  const config = useApi<{ configuration: Record<string,unknown>; provenance: string }>(`/config?${query({run_id:filters.run_id})}`)
  const [stage, setStage] = useState('analyze-signals')
  const [snapshot, setSnapshot] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [tab, setTab] = useState('pipeline')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const selectedStage = stages.data?.find(s => s.id === stage)
  const active = runs.data?.find(r => ['running','queued'].includes(r.status))
  const selected = runs.data?.find(r => r.id === selectedId)
  useEffect(() => { if (!selectedId && runs.data?.length) setSelectedId(runs.data[0].id) }, [selectedId,runs.data])
  async function launch() {
    setSubmitting(true);setError('');setSuccess('')
    try {
      const run = await api<Run>('/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stage,...(stage === 'bloomberg-import' ? {snapshot_date:snapshot}: {})})})
      setSelectedId(run.id);setSuccess(`${run.label} queued. Its output will be saved in a new run directory.`);runs.refresh();onLaunched()
    } catch (e) {setError((e as Error).message)}
    finally {setSubmitting(false)}
  }
  return <>
    <PageHeader eyebrow="EXPERIMENT OPERATIONS" title="Runs & configuration" description="Execute existing research stages with traceable, isolated outputs." actions={<Badge tone="blue"><GitBranch size={12} />Local job worker</Badge>} />
    <div className="tabs"><button className={tab === 'pipeline' ? 'selected':''} onClick={() => setTab('pipeline')}><CirclePlay size={15} />Pipeline runs</button><button className={tab === 'config' ? 'selected':''} onClick={() => setTab('config')}><Code2 size={15} />Configuration reference</button></div>
    {tab === 'config' ? config.loading ? <Loading /> : config.error ? <Failure message={config.error} /> : <Card><CardHeader title="Selected context configuration" subtitle={config.data?.provenance} /><pre className="document-preview">{JSON.stringify(config.data?.configuration,null,2)}</pre></Card> : <>
      <Note>Controls launch a new exploratory run from the repository’s current YAML configuration and canonical datasets. New outputs do not replace historical reports or promote a result to frozen confirmation. One pipeline job runs at a time. Data download remains available through the existing CLI.</Note>
      <div className="run-launch-grid"><Card><CardHeader title="Start a research stage" subtitle="Existing Python pipeline · fixed allowlist" /><div className="launch-form"><label>Pipeline stage<select aria-label="Pipeline stage" value={stage} onChange={e => {setStage(e.target.value);setError('');setSuccess('')}}>{stages.data?.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select></label><p>{selectedStage?.description}</p>{stage === 'bloomberg-import' && <label>Source snapshot date<input type="date" aria-label="Bloomberg snapshot date" value={snapshot} onChange={e => setSnapshot(e.target.value)} /><small>Must match the date of the repository XLSX files. File selection and arbitrary paths are not accepted.</small></label>}
      <div className="prerequisites">{selectedStage?.prerequisites.map(p => <span key={p}><Check size={12} />{p}</span>)}</div>
      {!selectedStage?.available && selectedStage?.reason && <Note tone="amber">{selectedStage.reason}</Note>}
      {active && <Note>A {active.stage} job is {active.status}. Launching is disabled until it finishes.</Note>}
      {error && <div className="inline-error" role="alert">{error}</div>}{success && <div className="inline-success" role="status">{success}</div>}
      <Button variant="default" disabled={submitting || !!active || !selectedStage?.available || (stage === 'bloomberg-import' && !snapshot)} onClick={launch}>{submitting ? <LoaderCircle size={15} className="spin" /> : <CirclePlay size={15} />}Launch new run</Button></div></Card>
      <Card><CardHeader title="Reproducibility by default" subtitle="Recorded for every dashboard execution" /><div className="workflow-list">{[['01','Snapshot','Store the exact configuration, input dataset hashes, and Git revision.'],['02','Execute','Run existing Python functions in an isolated background process.'],['03','Preserve','Save logs, timestamps, output checksums, and success or failure state.']].map(([n,title,text]) => <div key={n}><span>{n}</span><div><strong>{title}</strong><p>{text}</p></div></div>)}</div><div className="card-footnote"><Clock3 size={13} />No live trading or brokerage connection.</div></Card></div>
      <Card><CardHeader title="Run history" subtitle="Dashboard executions and original artifact groups · auto-refresh every 3s" />{runs.loading ? <Loading /> : runs.error ? <Failure message={runs.error} /> : <DataTable data={runs.data || []} pageSize={8} onRowClick={r => setSelectedId(r.id)} columns={[
        {accessorKey:'label',header:'Research run',cell:({row}) => <div className="signal-name"><strong>{row.original.label}</strong><small className="mono">{row.original.id.slice(0,22)}</small></div>},
        {accessorKey:'stage',header:'Stage',cell:({getValue}) => label(getValue())},
        {accessorKey:'created_at',header:'Created',cell:({getValue}) => timestamp(getValue() as string|null)},
        {accessorKey:'status',header:'Status',cell:({getValue}) => <Status value={String(getValue())} />},
        {accessorKey:'git_commit',header:'Git revision',cell:({getValue}) => <span className="mono muted">{getValue() ? String(getValue()).slice(0,8):'Not recorded'}</span>},
      ]} />}</Card>
      {selected && <RunDetail key={selected.id} run={selected} />}
    </>}
  </>
}
