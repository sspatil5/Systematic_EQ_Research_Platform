import { useState } from 'react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { ArrowDownToLine, ChevronRight, FileChartColumn, FileCode2, FileImage, FileSpreadsheet, FileText, Search, ShieldCheck, X } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Badge, Failure, Loading, Note, PageHeader, Status } from '../components/shared'
import { DataTable } from '../components/data-table'
import { api, label, query, size, timestamp, useApi } from '../lib'
import type { Artifact, ArtifactPage, ArtifactPreview, Filters, Integrity, Row } from '../types'

function FileIcon({ kind }: { kind: string }) {
  const Icon = ['csv','parquet','xlsx'].includes(kind) ? FileSpreadsheet : ['png','svg'].includes(kind) ? FileImage : ['json','yaml'].includes(kind) ? FileCode2 : FileText
  return <span className={`file-icon file-${kind}`}><Icon size={17} /></span>
}
function Preview({ artifact, runId, close }: { artifact: Artifact; runId: string; close: () => void }) {
  const result = useApi<ArtifactPreview>(`/artifacts/${artifact.id}/preview?${query({run_id:runId})}`)
  const [verification, setVerification] = useState<Integrity>()
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState('')
  async function verify() {
    setVerifying(true); setError('')
    try { setVerification(await api<Integrity>(`/artifacts/${artifact.id}/integrity?${query({run_id:runId})}`)) }
    catch (e) { setError((e as Error).message) }
    finally { setVerifying(false) }
  }
  return <Card className="artifact-preview"><CardHeader title={artifact.name} subtitle={artifact.location} action={<Button variant="ghost" size="icon" aria-label="Close preview" onClick={close}><X size={17} /></Button>} />
    <div className="artifact-meta"><span>{size(artifact.size)}</span><span>Modified {timestamp(artifact.modified_at)}</span><Badge>{artifact.kind.toUpperCase()}</Badge><Button size="sm" onClick={verify} disabled={verifying}><ShieldCheck size={14} />{verifying ? 'Computing…' : 'Check integrity'}</Button><Button asChild size="sm"><a href={`/api/artifacts/${artifact.id}/download?${query({run_id:runId})}`}><ArrowDownToLine size={14} />Download original</a></Button></div>
    {verification && <div className="integrity-result"><Status value={verification.status} /><code>{verification.actual_sha256}</code>{verification.status === 'unrecorded' && <p>Current digest computed. No recorded checksum exists, so historical integrity cannot be established.</p>}</div>}
    {error && <Note tone="amber">{error}</Note>}
    {result.loading ? <Loading /> : result.error ? <Failure message={result.error} retry={result.refresh} /> : result.data?.text !== null && result.data?.text !== undefined ? <pre className="document-preview">{result.data.text}</pre> : result.data?.columns.length ? <DataTable data={result.data.rows} columns={result.data.columns.map(key => ({accessorKey:key,header:key,cell:({getValue}) => { const value = getValue(); return value === null ? <span className="muted">—</span> : String(value) }})) as ColumnDef<Row>[]} pageSize={10} /> : artifact.kind === 'png' ? <div className="image-preview"><img src={`/api/artifacts/${artifact.id}/image?${query({run_id:runId})}`} alt={artifact.name} /></div> : <Note>This file is available as a download. Inline preview supports text reports, configurations, tables, and PNG figures.</Note>}
    {result.data?.truncated && <div className="card-footnote">Preview truncated. Download the original file for the complete artifact.</div>}
  </Card>
}
export function Reports({ filters }: { filters: Filters }) {
  const [search, setSearch] = useState('')
  const [group, setGroup] = useState('')
  const [kind, setKind] = useState('')
  const [page, setPage] = useState(1)
  const [sorting, setSorting] = useState<SortingState>([{id:'modified_at',desc:true}])
  const [selected, setSelected] = useState<Artifact>()
  const result = useApi<ArtifactPage>(`/artifacts?${query({run_id:filters.run_id, search, group, kind, page, page_size:15, sort:sorting[0]?.id || 'modified_at',descending:sorting[0]?.desc ?? true})}`)
  const columns: ColumnDef<Artifact>[] = [
    { accessorKey:'name', header:'Artifact', cell:({row}) => <span className="artifact-name"><FileIcon kind={row.original.kind} /><span><strong>{row.original.name}</strong><small>{row.original.location}</small></span></span> },
    { accessorKey:'group',header:'Research group',cell:({getValue}) => <Badge>{label(getValue())}</Badge> },
    { accessorKey:'kind',header:'Format',cell:({getValue}) => <span className="mono muted">{String(getValue()).toUpperCase()}</span> },
    { accessorKey:'size',header:'Size',cell:({getValue}) => <span className="mono">{size(Number(getValue()))}</span> },
    { accessorKey:'modified_at',header:'Modified',cell:({getValue}) => <span className="muted">{timestamp(String(getValue()))}</span> },
    { accessorKey:'recorded_sha256',header:'Recorded hash',cell:({getValue}) => <Badge tone={getValue() ? 'green':'neutral'}>{getValue() ? 'Available':'Unrecorded'}</Badge> },
    { id:'open',header:'',enableSorting:false,cell:() => <ChevronRight size={15} className="muted" /> },
  ]
  return <>
    <PageHeader eyebrow="REPRODUCIBILITY" title="Reports & audit" description="Trace every result to the original research artifact." actions={<Badge tone="blue"><FileChartColumn size={12} />{result.data?.total ?? '—'} matching artifacts</Badge>} />
    <Note>Artifact groups follow the selected run. Strategy, sample, and date filters do not alter original files. Historical modification times are file metadata, not experiment execution times.</Note>
    <Card><CardHeader title="Artifact library" subtitle="Reports, datasets, statistical outputs, figures, and configuration files" /><div className="filter-toolbar"><label className="search-field"><Search size={15} /><input placeholder="Search files and reports…" aria-label="Search artifacts" value={search} onChange={e => {setSearch(e.target.value);setPage(1)}} /></label><select aria-label="Artifact group" value={group} onChange={e => {setGroup(e.target.value);setPage(1)}}><option value="">All research groups</option>{result.data?.groups.map(g => <option key={g} value={g}>{label(g)}</option>)}</select><select aria-label="Artifact format" value={kind} onChange={e => {setKind(e.target.value);setPage(1)}}><option value="">All file formats</option>{['md','csv','parquet','png','json','yaml','xlsx','docx'].map(k => <option key={k} value={k}>{k.toUpperCase()}</option>)}</select></div>
      {result.loading ? <Loading /> : result.error ? <Failure message={result.error} retry={result.refresh} /> : <DataTable data={result.data?.items || []} columns={columns} pageSize={15} sorting={sorting} onSortingChange={update => {setSorting(update);setPage(1)}} serverPage={page} total={result.data?.total} onPageChange={setPage} onRowClick={setSelected} />}
    </Card>
    {selected && <Preview key={selected.id} artifact={selected} runId={filters.run_id} close={() => setSelected(undefined)} />}
  </>
}
