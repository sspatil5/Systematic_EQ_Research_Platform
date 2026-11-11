import { useState } from 'react'
import { ArrowDownToLine, Settings2 } from 'lucide-react'
import { Card, CardHeader } from '../components/ui/card'
import { Badge, Download, Empty, Failure, Loading, Metrics, Note, PageHeader } from '../components/shared'
import { Bars, EquityChart, Legend, LineChartPanel } from '../components/charts'
import { fmt, label, number, pct, query, shortDate, useApi } from '../lib'
import type { Backtest, Filters } from '../types'

export function Backtests({ filters }: { filters: Filters }) {
  const { data, loading, error, refresh } = useApi<Backtest>(`/backtest?${query(filters)}`)
  const [showConfig, setShowConfig] = useState(false)
  const [mode, setMode] = useState('equity')
  if (loading) return <Loading />
  if (error || !data) return <Failure message={error || 'No backtest response'} retry={refresh} />
  const years = [...new Set(data.monthly.map(row => Number(row.year)))].sort((a,b) => b-a)
  return <>
    <PageHeader eyebrow="HISTORICAL SIMULATION" title="Backtest results" description="Portfolio performance, execution assumptions, and risk diagnostics." actions={<><button className="button button-secondary" onClick={() => setShowConfig(!showConfig)}><Settings2 size={14} />Run configuration</button><Download rows={[data.metrics]} filename="backtest-metrics.csv"><ArrowDownToLine size={14} />Export metrics</Download></>} />
    <div className="backtest-context"><div><Badge tone="blue">Historical backtest</Badge><strong>{label(filters.strategy)}</strong><span className="muted">{shortDate(data.metrics.start)} → {shortDate(data.metrics.end)}</span></div><span>{fmt(data.metrics.observations,0)} sessions · {label(filters.period).toLowerCase()} sample</span></div>
    {data.available ? <>
      <Metrics metrics={data.metrics} extended />
      {showConfig && <Card><CardHeader title="Configuration & immutable research definition" subtitle={data.configuration_provenance} /><div className="config-grid">{Object.entries(data.configuration).map(([key,value]) => <div key={key}><span>{label(key)}</span><strong>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</strong></div>)}</div>{data.freeze_definition && <details className="freeze-details"><summary>Read frozen historical methodology</summary><pre>{data.freeze_definition}</pre></details>}<Note>Signal observed after close; execution follows the saved run's timing. Phase 4 uses long-only whole adjusted-share units without leverage or shorting. Historical adjustments, missing observations, static constituents, and estimated costs limit the simulation.</Note></Card>}
      <Card className="backtest-equity"><CardHeader title="Portfolio & benchmark performance" subtitle="Each selected sample normalized to the original starting capital · USD" action={<div className="segmented"><button className={mode === 'equity' ? 'selected' : ''} onClick={() => setMode('equity')}>Equity curve</button><button className={mode === 'returns' ? 'selected' : ''} onClick={() => setMode('returns')}>Return</button></div>} /><EquityChart data={data.curve} initialCapital={data.initial_capital} normalized={mode === 'returns'} /><div className="chart-bottom"><Legend /><Download rows={data.curve} filename="equity-curve.csv">Export series</Download></div></Card>
      <div className="two-column"><Card><CardHeader title="Underwater drawdown" subtitle="Decline from the running portfolio peak · selected sample" /><LineChartPanel data={data.curve} dataKey="drawdown" label="Drawdown" color="#ef7384" percent area /></Card><Card><CardHeader title="Rolling Sharpe ratio" subtitle="126 trading sessions · zero risk-free rate" /><LineChartPanel data={data.curve} dataKey="rolling_sharpe" label="Sharpe" color="#4bd8b1" /></Card></div>
      <div className="two-column"><Card><CardHeader title="Rolling volatility" subtitle="126-session sample standard deviation · annualized" /><LineChartPanel data={data.curve} dataKey="rolling_volatility" label="Annualized volatility" color="#b39adf" percent /></Card><Card><CardHeader title="Rolling market beta" subtitle="126-session covariance / SPY variance" /><LineChartPanel data={data.curve} dataKey="rolling_beta" label="Beta to SPY" /></Card></div>
      <Card><CardHeader title="Monthly returns" subtitle="Compounded saved net returns · calendar months" action={<div className="heatmap-key"><span>Negative</span><i /><span>Positive</span></div>} /><div className="heatmap-scroll"><table className="monthly-table"><thead><tr><th>YEAR</th>{['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'].map(m => <th key={m}>{m}</th>)}<th>YEAR</th></tr></thead><tbody>{years.map(year => <tr key={year}><th>{year}</th>{Array.from({length:12}, (_,i) => {
        const row = data.monthly.find(r => r.year === year && r.month === i+1)
        const value = number(row?.return)
        return <td key={i}><span style={{ background: value === null ? 'transparent' : value >= 0 ? `rgba(75,216,177,${Math.min(Math.abs(value)*4+0.06,0.65)})` : `rgba(239,115,132,${Math.min(Math.abs(value)*4+0.06,0.65)})` }} title={`${year}-${String(i+1).padStart(2,'0')}: ${pct(value)}`}>{pct(value,1)}</span></td>
      })}<td className="annual-value">{pct(data.annual.find(r => r.year === year)?.portfolio,1)}</td></tr>)}</tbody></table></div></Card>
      <Card><CardHeader title="Annual performance comparison" subtitle="Portfolio, SPY, and eligible equal-weight benchmark · selected dates" action={<Legend />} /><Bars data={data.annual} xKey="year" keys={[{ key:'portfolio',name:'Portfolio',color:'#4bd8b1' },{ key:'spy',name:'SPY',color:'#789cfa' },{ key:'equal_weight',name:'Equal weight',color:'#b39adf' }]} /></Card>
      <Note>{data.metrics_source} Rolling metrics require 126 observations within the selected date range. Ending value is normalized for each sample; the historical account is not reset between samples.</Note>
    </> : <Empty title="No backtest output in this context" description="Choose repository artifacts or a completed realistic backtest run. Missing results are never inferred." />}
    <Note tone="amber">{data.warnings.join(' ')}</Note>
  </>
}
