import { useMemo, useState } from 'react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { AlertTriangle, Database, FileSpreadsheet, Search } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/card'
import { DataTable } from '../components/data-table'
import { Badge, Download, Failure, Loading, Note, PageHeader, Status } from '../components/shared'
import { fmt, money, pct, query, shortDate, useApi } from '../lib'
import type { Dataset, Filters, ImportStatus, Row, TablePage } from '../types'
import { Button } from '../components/ui/button'

export function Universe({ filters, navigate }: { filters: Filters; navigate: (page: string) => void }) {
  const [tab, setTab] = useState('universe')
  const [search, setSearch] = useState('')
  const [sector, setSector] = useState('')
  const [liquidity, setLiquidity] = useState('0')
  const [page, setPage] = useState(1)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'ticker', desc: false }])
  const dataset = useApi<Dataset>(`/dataset?${query(filters)}`)
  const table = useApi<TablePage>(`/universe?${query({ run_id: filters.run_id, period: filters.period, start: filters.start, end: filters.end, search, sector, minimum_liquidity: liquidity, page, page_size: 15, sort: sorting[0]?.id || 'ticker', descending: sorting[0]?.desc || false })}`)
  const imports = useApi<ImportStatus>('/bloomberg')
  const columns = useMemo<ColumnDef<Row>[]>(() => [
    { accessorKey: 'ticker', header: 'Ticker', cell: ({ getValue }) => <span className="ticker-cell"><span>{String(getValue()).slice(0,2)}</span><strong>{String(getValue())}</strong></span> },
    { accessorKey: 'sector', header: 'Sector' },
    { accessorKey: 'start', header: 'First observation', cell: ({ getValue }) => <span className="mono muted">{shortDate(getValue())}</span> },
    { accessorKey: 'end', header: 'Last observation', cell: ({ getValue }) => <span className="mono muted">{shortDate(getValue())}</span> },
    { accessorKey: 'observations', header: 'Observations', cell: ({ getValue }) => <span className="mono">{fmt(getValue(), 0)}</span> },
    { accessorKey: 'missing_fraction', header: 'Missing sessions', cell: ({ getValue }) => <span className="mono">{pct(getValue())}</span> },
    { accessorKey: 'dollar_volume_20', header: '20d dollar volume', cell: ({ getValue }) => <span className="mono">{money(getValue(), true)}</span> },
    { accessorKey: 'liquidity_eligible', header: 'Liquidity', cell: ({ getValue }) => <Badge tone={getValue() ? 'green' : 'amber'}>{getValue() === null ? 'Unknown' : getValue() ? 'Above floor' : 'Below floor'}</Badge> },
  ], [])
  function reset(change: () => void) { change(); setPage(1) }
  return <>
    <PageHeader eyebrow="DATA INFRASTRUCTURE" title="Data & universe" description="Inspect your market dataset, coverage, and security-master validation." actions={<Download rows={table.data?.items || []} filename="universe-page.csv">Export current page</Download>} />
    <div className="tabs"><button className={tab === 'universe' ? 'selected' : ''} onClick={() => setTab('universe')}><Database size={15} />Market universe<Badge>{dataset.data?.securities ?? '—'}</Badge></button><button className={tab === 'bloomberg' ? 'selected' : ''} onClick={() => setTab('bloomberg')}><FileSpreadsheet size={15} />Bloomberg importer<Badge tone="amber">Validation</Badge></button></div>
    {tab === 'universe' ? <>
      <div className="small-stat-grid"><Card><span>Securities</span><strong>{fmt(dataset.data?.securities, 0)}</strong><small>Static development universe</small></Card><Card><span>Panel observations</span><strong>{fmt(dataset.data?.rows, 0)}</strong><small>Adjusted daily OHLCV</small></Card><Card><span>Panel coverage</span><strong>{pct(dataset.data?.coverage)}</strong><small>Observed / expected ticker-sessions</small></Card><Card><span>Latest market date</span><strong>{shortDate(dataset.data?.end)}</strong><small>{dataset.data?.freshness_days ?? '—'} calendar days old</small></Card></div>
      <Card><CardHeader title="Security coverage" subtitle="Search and filter source observations" /><div className="filter-toolbar"><label className="search-field"><Search size={15} /><input aria-label="Search tickers" placeholder="Search tickers…" value={search} onChange={e => reset(() => setSearch(e.target.value))} /></label><select aria-label="Sector" value={sector} onChange={e => reset(() => setSector(e.target.value))}><option value="">All sectors</option>{dataset.data?.sectors.map(s => <option key={s}>{s}</option>)}</select><select aria-label="Liquidity filter" value={liquidity} onChange={e => reset(() => setLiquidity(e.target.value))}><option value="0">All liquidity levels</option><option value="20000000">Dollar volume ≥ $20M</option><option value="100000000">Dollar volume ≥ $100M</option></select></div>
      {table.loading ? <Loading /> : table.error ? <Failure message={table.error} retry={table.refresh} /> : <DataTable data={table.data?.items || []} columns={columns} sorting={sorting} onSortingChange={update => { setSorting(update); setPage(1) }} serverPage={page} total={table.data?.total} pageSize={15} onPageChange={setPage} />}</Card>
      <Note>{table.data?.note || 'Coverage is calculated from the selected canonical panel dates.'} Sector labels are cached current classifications. Source: {dataset.data?.source}.</Note>
    </> : imports.loading ? <Loading /> : imports.error || !imports.data ? <Failure message={imports.error || 'Import diagnostics unavailable'} /> : <>
      <Card className="import-alert"><AlertTriangle size={22} /><div><h2>Security-master import {imports.data.status}</h2><p>Source snapshot {imports.data.snapshot_date}. Critical data checks remain enforced. Raw diagnostics do not authorize an eligible universe.</p></div><Status value={imports.data.status} /></Card>
      <div className="small-stat-grid"><Card><span>Raw source rows</span><strong>{fmt(imports.data.summary.combined_raw_rows, 0)}</strong><small>Across {imports.data.source_files.length} XLSX files</small></Card><Card><span>Unique FIGIs</span><strong>{fmt(imports.data.summary.unique_figis, 0)}</strong><small>Diagnostic identities only</small></Card><Card><span>Ticker mapping</span><strong>{pct(imports.data.summary.ticker_mapping_success_rate)}</strong><small>Raw source mapping coverage</small></Card><Card><span>Conflicting FIGIs</span><strong className="amber-text">{fmt(imports.data.summary.conflicting_figis, 0)}</strong><small>Import requires review</small></Card></div>
      <div className="two-column"><Card><CardHeader title="Critical validation failures" subtitle="Required schema checks · fail closed" /><div className="detail-list">{imports.data.errors.map(e => <div key={e} className="validation-error"><AlertTriangle size={15} /><span>{e}</span></div>)}{!imports.data.errors.length && <p>No critical schema errors recorded.</p>}</div><div className="card-footnote">Unresolved ticker details and a normalized security master are unavailable in the failed import output.</div></Card><Card><CardHeader title="Registered source files" subtitle="Fixed repository source set" /><div className="detail-list">{imports.data.source_files.map(file => <div className="source-file" key={file}><FileSpreadsheet size={16} /><span>{file}</span></div>)}</div><div className="card-footer"><Button onClick={() => navigate('runs')}>Open import controls</Button></div></Card></div>
      <Card><CardHeader title="Import history" subtitle="Recorded audit events · original timestamps" /><DataTable data={imports.data.history} pageSize={8} columns={[
        { accessorKey: 'timestamp', header: 'Timestamp', cell: ({ getValue }) => <span className="mono">{String(getValue()).slice(0,19).replace('T',' ')} UTC</span> },
        { accessorKey: 'event_type', header: 'Event' }, { accessorKey: 'signal_date', header: 'Snapshot date' },
        { accessorKey: 'status', header: 'Status', cell: ({ getValue }) => <Status value={String(getValue())} /> },
      ]} /></Card>
    </>}
  </>
}
