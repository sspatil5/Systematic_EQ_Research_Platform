import { useMemo, useState } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { Activity, ArrowUpRight } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/card'
import { DataTable } from '../components/data-table'
import { Badge, Download, Empty, Failure, Loading, Note, PageHeader } from '../components/shared'
import { Bars, LineChartPanel } from '../components/charts'
import { fmt, label, number, pct, query, useApi } from '../lib'
import type { Filters, Row, SignalData } from '../types'

function Evidence({ value }: { value: unknown }) {
  const text = String(value || 'Unclassified')
  return <Badge tone={text === 'REJECT' ? 'red' : /PROMISING|STRONG/.test(text) ? 'green' : 'amber'}>{text === 'WEAK / INCONCLUSIVE' ? 'Weak / inconclusive' : label(text).toLowerCase()}</Badge>
}
export function Signals({ filters }: { filters: Filters }) {
  const [signal, setSignal] = useState('')
  const result = useApi<SignalData>(`/signals?${query({ run_id: filters.run_id, period: filters.period, start: filters.start, end: filters.end, signal })}`)
  const columns = useMemo<ColumnDef<Row>[]>(() => [
    { accessorKey: 'signal', header: 'Signal', cell: ({ row }) => <div className="signal-name" title={String(row.original.description)}><strong>{label(row.original.signal)}</strong><small>{row.original.lookback ? `${row.original.lookback} session lookback` : label(row.original.category || row.original.family)} <ArrowUpRight size={10} /></small></div> },
    { accessorKey: 'mean_rank_ic', header: 'Rank IC', cell: ({ getValue }) => <span className="mono bright">{fmt(getValue(), 4)}</span> },
    { accessorKey: 'hac_t_stat', header: 'HAC t-stat', cell: ({ getValue }) => <span className="mono">{fmt(getValue(), 3)}</span> },
    { accessorKey: 'raw_p_value', header: 'p-value', cell: ({ getValue }) => <span className="mono">{fmt(getValue(), 4)}</span> },
    { accessorKey: 'fdr_q_value', header: 'FDR q-value', cell: ({ getValue }) => <span className="mono">{fmt(getValue(), 4)}</span> },
    { accessorKey: 'turnover', header: 'Turnover', cell: ({ getValue }) => <span className="mono">{pct(getValue(), 1)}</span> },
    { accessorKey: 'liquidity_robustness', header: 'Liquid IC', cell: ({ getValue }) => <span className="mono">{fmt(getValue(), 4)}</span> },
    { accessorKey: 'development_ic', header: 'Dev IC', cell: ({ getValue }) => <span className="mono">{fmt(getValue(), 4)}</span> },
    { accessorKey: 'confirmation_ic', header: 'Confirm IC', cell: ({ getValue }) => <span className="mono">{fmt(getValue(), 4)}</span> },
    { accessorKey: 'classification', header: 'Evidence', cell: ({ getValue }) => <Evidence value={getValue()} /> },
  ], [])
  if (result.loading) return <Loading />
  if (result.error || !result.data) return <Failure message={result.error || 'No signal response'} retry={result.refresh} />
  const data = result.data
  const selected = signal && data.scorecard.some(row => row.signal === signal) ? signal : String(data.scorecard[0]?.signal || '')
  return <>
    <PageHeader eyebrow="ALPHA RESEARCH" title="Signal research" description="Evaluate cross-sectional evidence before making portfolio decisions." actions={<Download rows={data.scorecard} filename="signal-scorecard.csv" />} />
    <Note tone="amber">{data.note}</Note>
    <Card><CardHeader title="Signal scorecard" subtitle={`${data.source} · ${data.scorecard.length} signals · click a row to inspect`} action={<Badge tone="blue"><Activity size={11} />5-session target</Badge>} />
      <DataTable data={data.scorecard} columns={columns} searchPlaceholder="Search signals…" pageSize={8} onRowClick={row => setSignal(String(row.signal))} />
    </Card>
    {data.available ? <>
      <div className="section-heading"><div><h2>Signal diagnostics</h2><Badge>Computed evidence</Badge></div><select aria-label="Selected signal" value={selected} onChange={e => setSignal(e.target.value)}>{data.scorecard.map(row => <option value={String(row.signal)} key={String(row.signal)}>{label(row.signal)}</option>)}</select></div>
      <div className="two-column"><Card><CardHeader title="Daily information coefficient" subtitle={`${label(selected)} · Spearman rank IC · selected dates`} /><LineChartPanel data={data.daily_ic} dataKey="spearman_ic" label="Spearman IC" /></Card><Card><CardHeader title="Forecast horizon decay" subtitle="Mean rank IC · stored full Phase 3 sample" /><LineChartPanel data={data.decay} xKey="horizon" dataKey="mean_rank_ic" color="#4bd8b1" label="Mean rank IC" /></Card></div>
      <div className="two-column"><Card><CardHeader title="Returns by quantile" subtitle="Mean 5-session forward return · research diagnostic" /><Bars data={data.quantiles} xKey="quantile" keys={[{ key: 'return', name: 'Forward return', color: '#789cfa' }]} /></Card><Card><CardHeader title="Statistical significance" subtitle="Absolute Newey–West t-statistic · complete stored sample" /><Bars data={data.scorecard.slice(0, 8).map(row => ({ signal: String(row.signal).replaceAll('_', ' ').slice(0,12), t: number(row.hac_t_stat) === null ? null : Math.abs(Number(row.hac_t_stat)) }))} xKey="signal" percent={false} keys={[{ key: 't', name: '|HAC t-stat|', color: '#b39adf' }]} /></Card></div>
      <Card><CardHeader title="Signal correlation matrix" subtitle="Average daily cross-sectional correlation · stored full Phase 3 sample" />{data.correlations.length ? <div className="heatmap-scroll"><table className="correlation-table"><thead><tr><th /><th colSpan={data.correlations.length}>Signals · hover a cell for exact correlation</th></tr><tr><th /><>{data.correlations.map(row => <th key={String(row.signal)} title={label(row.signal)}>{String(row.signal).replaceAll('relative_', 'rel_').slice(0,11)}</th>)}</></tr></thead><tbody>{data.correlations.map(row => <tr key={String(row.signal)}><th>{String(row.signal)}</th>{data.correlations.map(col => {
        const value = number(row[String(col.signal)])
        return <td key={String(col.signal)} title={`${row.signal} × ${col.signal}: ${fmt(value, 4)}`} style={{ background: value === null ? undefined : value >= 0 ? `rgba(75,216,177,${Math.abs(value)*0.65+0.04})` : `rgba(239,115,132,${Math.abs(value)*0.65+0.04})` }}>{fmt(value, 1)}</td>
      })}</tr>)}</tbody></table></div> : <Empty title="Correlation matrix unavailable for this sample" />}</Card>
    </> : <Empty title="No stored signal diagnostics" description="Select repository artifacts or a completed signal research run." />}
  </>
}
