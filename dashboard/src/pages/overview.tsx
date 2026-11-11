import { ArrowDownToLine, ArrowRight, ArrowUpRight, Clock3, Database, GitBranch, Layers3, ShieldAlert, ShieldCheck } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Badge, Download, Empty, Failure, Loading, Metrics, PageHeader, Status } from '../components/shared'
import { EquityChart, Legend } from '../components/charts'
import { fmt, label, money, pct, query, shortDate, timestamp, useApi } from '../lib'
import type { Filters, OverviewData } from '../types'
import { useState } from 'react'

export function Overview({ filters, navigate }: { filters: Filters; navigate: (page: string) => void }) {
  const { data, loading, error, refresh } = useApi<OverviewData>(`/overview?${query(filters)}`)
  const [chartMode, setChartMode] = useState('value')
  if (loading) return <Loading />
  if (error || !data) return <Failure message={error || 'No response from API'} retry={refresh} />
  const { dataset, backtest } = data
  return <>
    <PageHeader eyebrow="RESEARCH WORKSPACE" title="Research overview" description="A clear view of your systematic equity research." actions={<><Button onClick={() => navigate('reports')}><ArrowDownToLine size={14} />Browse reports</Button><Button variant="default" onClick={() => navigate('runs')}><GitBranch size={14} />New research run</Button></>} />
    <div className="status-strip">
      <div><Database size={15} /><span>Market data</span><strong>{shortDate(dataset.end)}</strong></div>
      <div><Layers3 size={15} /><span>Universe</span><strong>{dataset.securities} securities</strong></div>
      <div><ShieldCheck size={15} /><span>Panel coverage</span><strong>{pct(dataset.coverage, 2)}</strong></div>
      <div><Clock3 size={15} /><span>Latest recorded event</span><strong>{label(data.latest_pipeline_status)}</strong></div>
    </div>
    <div className="section-heading"><div><h2>Portfolio performance</h2><Badge tone="blue">Historical backtest</Badge></div><span>{label(filters.strategy)} strategy <span className="separator">/</span> {label(filters.period).toLowerCase()} sample <span className="separator">/</span> {shortDate(backtest.metrics.start)} — {shortDate(backtest.metrics.end)}</span></div>
    <Metrics metrics={backtest.metrics} />
    <div className="secondary-metrics"><div><span>Annualized volatility</span><strong>{pct(backtest.metrics.annualized_volatility)}</strong></div><div><span>Annual turnover</span><strong>{backtest.metrics.annual_turnover == null ? '—' : `${fmt(backtest.metrics.annual_turnover)}×`}</strong></div><div><span>Estimated transaction costs</span><strong>{money(backtest.metrics.estimated_costs)}</strong></div><div><span>SPY annualized return</span><strong>{pct(backtest.metrics.spy_cagr)}</strong></div></div>
    <div className="overview-main-grid">
      <Card className="equity-card"><CardHeader title="Portfolio growth" subtitle="Simulated portfolio and benchmarks · USD" action={<div className="segmented"><button className={chartMode === 'value' ? 'selected' : ''} onClick={() => setChartMode('value')}>Value</button><button className={chartMode === 'return' ? 'selected' : ''} onClick={() => setChartMode('return')}>Return</button></div>} />
        {backtest.available ? <EquityChart data={backtest.curve} initialCapital={backtest.initial_capital} normalized={chartMode === 'return'} /> : <Empty title="Backtest unavailable for this run" />}
        <div className="chart-bottom"><Legend /><button className="text-link" onClick={() => navigate('backtests')}>Explore backtest <ArrowUpRight size={13} /></button></div>
      </Card>
      <Card className="research-health"><CardHeader title="Research integrity" subtitle="Data and methodology checkpoints" action={<ShieldCheck size={17} className="muted" />} />
        <div className="integrity-item"><span className="integrity-icon blue"><Database size={16} /></span><div><strong>Canonical dataset</strong><p>{fmt(dataset.rows, 0)} observations</p></div><Badge tone="blue">{dataset.available ? 'Available' : 'Missing'}</Badge></div>
        <div className="integrity-item"><span className="integrity-icon amber"><Clock3 size={16} /></span><div><strong>Data freshness</strong><p>{dataset.freshness_days === null ? 'No data' : `${dataset.freshness_days} calendar days since last bar`}</p></div><Badge tone={(dataset.freshness_days || 0) > 7 ? 'amber' : 'green'}>{(dataset.freshness_days || 0) > 7 ? 'Review' : 'Recent'}</Badge></div>
        <div className="integrity-item"><span className="integrity-icon amber"><ShieldAlert size={16} /></span><div><strong>Point-in-time universe</strong><p>Current constituents selected today</p></div><Badge tone="amber">Biased</Badge></div>
        <div className="health-footer"><span className="status-dot" />Research environment only<p>Historical and exploratory outputs.<br />Prospective monitoring is unavailable.</p></div>
      </Card>
    </div>
    <div className="overview-bottom-grid">
      <Card><CardHeader title="Research activity" subtitle="Saved artifacts and dashboard executions" action={<button className="text-link" onClick={() => navigate('runs')}>All runs <ArrowRight size={13} /></button>} />
        <div className="activity-list">{data.runs.slice(0,4).map(run => <div className="activity-item" key={run.id}><span className="activity-icon"><GitBranch size={15} /></span><div><strong>{run.label}</strong><p>{run.status === 'historical' ? run.output_location : timestamp(run.created_at)}</p></div><Status value={run.status} /></div>)}{!data.runs.length && <Empty title="No recorded research runs" />}</div>
        <div className="card-footnote">Historical artifact groups have no recorded original execution timestamp.</div>
      </Card>
      <Card><CardHeader title="Signal snapshot" subtitle={filters.period === 'FULL' ? 'Phase 3 · ranked by absolute information coefficient' : `Phase 3.5 · ${filters.period.toLowerCase()} evidence`} action={<button className="text-link" onClick={() => navigate('signals')}>Explore <ArrowRight size={13} /></button>} />
        <div className="signal-mini-header"><span>SIGNAL</span><span>MEAN RANK IC</span></div>
        {data.signals.map(row => <div className="signal-mini-row" key={String(row.signal)}><div><strong>{label(row.signal)}</strong><span>{label(row.classification)}</span></div><div className="signal-mini-value"><div className="signal-bar"><i style={{ width: `${Math.min(Math.abs(Number(row.mean_rank_ic)) * 1200, 100)}%` }} /></div><span>{fmt(row.mean_rank_ic, 4)}</span></div></div>)}
        {!data.signals.length && <Empty title="Signal diagnostics unavailable" />}
      </Card>
    </div>
    <Card className="warning-card"><div className="warning-heading"><ShieldAlert size={16} /><h2>Research notes & data quality</h2><Badge tone="amber">{data.warnings.length} observations</Badge></div><div className="warning-list">{data.warnings.map((warning, index) => <p key={warning}><span>{String(index+1).padStart(2, '0')}</span>{warning}</p>)}</div></Card>
    <div className="page-footnote"><span><span className="status-dot" />Actual repository artifacts · no synthetic metrics</span><Download rows={[backtest.metrics]} filename="backtest-summary.csv">Export summary</Download></div>
  </>
}
