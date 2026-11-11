import { AlertCircle, ArrowDownToLine, ArrowUpRight, CircleHelp, Database, LoaderCircle, RefreshCw } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from './ui/button'
import { Card } from './ui/card'
import { cn, exportCsv, fmt, money, number, pct } from '../lib'
import type { Row } from '../types'

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'green' | 'red' | 'amber' | 'blue' | 'neutral' }) {
  return <span className={cn('badge', `badge-${tone}`)}>{children}</span>
}
export function Status({ value }: { value: string }) {
  const tone = /^(succeeded|success|verified|complete)$/i.test(value) ? 'green' : /failed|invalid|mismatch|reject/i.test(value) ? 'red' : /running|queued/i.test(value) ? 'blue' : /incomplete/i.test(value) ? 'amber' : 'neutral'
  return <Badge tone={tone}><span className="status-dot" />{value.replaceAll('_', ' ')}</Badge>
}
export function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div><div className="page-actions">{actions}</div></div>
}
export function Loading() { return <div className="loading" role="status"><LoaderCircle size={22} className="spin" /><span>Reading research artifacts…</span></div> }
export function Failure({ message, retry }: { message: string; retry?: () => void }) {
  return <Card className="empty-state" role="alert"><AlertCircle size={28} /><h2>Unable to load this view</h2><p>{message}</p>{retry && <Button onClick={retry}><RefreshCw size={14} />Retry request</Button>}</Card>
}
export function Empty({ title = 'No results available', description = 'Choose another research run or date range.' }: { title?: string; description?: string }) {
  return <div className="empty-state"><Database size={27} /><h3>{title}</h3><p>{description}</p></div>
}
export function Note({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'amber' }) {
  return <div className={cn('note', tone === 'amber' && 'note-amber')}><CircleHelp size={15} /><div>{children}</div></div>
}
export function Download({ rows, filename = 'research-export.csv', children = 'Export CSV' }: { rows: Record<string, unknown>[]; filename?: string; children?: ReactNode }) {
  return <Button onClick={() => exportCsv(rows, filename)} disabled={!rows.length}><ArrowDownToLine size={14} />{children}</Button>
}
const metricDefinitions = [
  { key: 'cagr', title: 'Annualized return', format: pct, help: 'CAGR · 252 sessions / year', className: 'green-text' },
  { key: 'zero_rate_sharpe', title: 'Sharpe ratio', format: fmt, help: 'Annualized · zero risk-free rate', className: '' },
  { key: 'max_drawdown', title: 'Max drawdown', format: pct, help: 'Largest peak-to-trough decline', className: 'red-text' },
  { key: 'ending_equity', title: 'Ending portfolio value', format: money, help: 'Normalized to starting capital', className: '' },
]
export function Metrics({ metrics, extended = false }: { metrics: Row; extended?: boolean }) {
  const extras = [
    { key: 'annualized_volatility', title: 'Annualized volatility', format: pct, help: 'Daily sample volatility × √252', className: '' },
    { key: 'annual_turnover', title: 'Annual turnover', format: (v: unknown) => `${fmt(v)}×`, help: 'Gross traded notional / equity', className: '' },
    { key: 'estimated_costs', title: 'Transaction costs', format: money, help: 'Estimated across selected period', className: '' },
    { key: 'beta_to_spy', title: 'Market beta', format: fmt, help: 'Exposure relative to SPY', className: '' },
  ]
  return <div className="metric-grid">{[...metricDefinitions, ...(extended ? extras : [])].map((m, i) => <Card className="metric-card" key={m.key}>
    <div className="metric-label">{m.title}<span title={m.help}><CircleHelp size={13} /></span></div>
    <div className={cn('metric-value', m.className)}>{number(metrics[m.key]) === null ? '—' : m.format(metrics[m.key])}</div>
    <div className="metric-foot">{i === 0 && number(metrics.spy_cagr) !== null ? <><ArrowUpRight size={12} />SPY {pct(metrics.spy_cagr)} <span className="muted">CAGR</span></> : m.help}</div>
  </Card>)}</div>
}
