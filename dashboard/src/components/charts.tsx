import { useId } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Row } from '../types'
import { fmt, money, pct } from '../lib'
import { Empty } from './shared'

const colors = { portfolio: '#4bd8b1', spy: '#789cfa', equal_weight: '#b39adf' }
const grid = '#202b3a'
const axis = { fontSize: 10, fill: '#7d8b9e', fontFamily: 'ui-monospace, SFMono-Regular, monospace' }
const tooltip = { background: '#151e2c', border: '1px solid #2b394b', borderRadius: 6, color: '#dce5ef', fontSize: 12 }
export function EquityChart({ data, normalized = false, initialCapital, series = ['portfolio', 'spy', 'equal_weight'] }: { data: Row[]; normalized?: boolean; initialCapital?: number | null; series?: string[] }) {
  const id = useId().replaceAll(':', '')
  if (!data.length) return <Empty title="No equity series available" />
  const first = data[0]
  const chartData = normalized ? data.map(row => ({ ...row, ...Object.fromEntries(series.map(s => [s, typeof row[s] === 'number' && typeof first[s] === 'number' ? ((row[s] as number) / (initialCapital || (first[s] as number)) - 1) : null])) })) : data
  return <div className="chart"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={chartData} margin={{ top: 10, right: 14, left: 0, bottom: 0 }}>
    <defs><linearGradient id={`equity-${id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4bd8b1" stopOpacity={0.13} /><stop offset="100%" stopColor="#4bd8b1" stopOpacity={0} /></linearGradient></defs>
    <CartesianGrid stroke={grid} strokeDasharray="3 5" vertical={false} />
    <XAxis dataKey="date" tick={axis} axisLine={false} tickLine={false} minTickGap={55} tickFormatter={v => String(v).slice(0, 4)} />
    <YAxis tick={axis} axisLine={false} tickLine={false} width={64} tickFormatter={v => normalized ? pct(v, 0) : money(v, true)} />
    <Tooltip contentStyle={tooltip} labelFormatter={v => String(v).slice(0,10)} formatter={(v, name) => [normalized ? pct(v) : money(v), name]} />
    {series.includes('portfolio') && <Area type="linear" dataKey="portfolio" name="Portfolio" fill={`url(#equity-${id})`} stroke={colors.portfolio} strokeWidth={2} isAnimationActive={false} />}
    {series.includes('spy') && <Line type="linear" dataKey="spy" name="SPY" stroke={colors.spy} dot={false} strokeWidth={1.5} isAnimationActive={false} />}
    {series.includes('equal_weight') && <Line type="linear" dataKey="equal_weight" name="Equal weight" stroke={colors.equal_weight} dot={false} strokeWidth={1.3} strokeDasharray="4 3" isAnimationActive={false} />}
  </ComposedChart></ResponsiveContainer></div>
}
export function LineChartPanel({ data, dataKey, color = '#789cfa', percent = false, label = 'Value', xKey = 'date', area = false }: { data: Row[]; dataKey: string; color?: string; percent?: boolean; label?: string; xKey?: string; area?: boolean }) {
  if (!data.length) return <Empty title="No stored series available" description="This diagnostic has not been generated for the selected signal or run." />
  return <div className="chart chart-small"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data} margin={{ top: 10, right: 15, left: 0, bottom: 0 }}>
    <CartesianGrid stroke={grid} strokeDasharray="3 5" vertical={false} />
    <XAxis dataKey={xKey} tick={axis} axisLine={false} tickLine={false} minTickGap={45} tickFormatter={v => xKey === 'date' ? String(v).slice(0, 4) : `${v}d`} />
    <YAxis tick={axis} axisLine={false} tickLine={false} width={55} tickFormatter={v => percent ? pct(v, 0) : fmt(v, 1)} />
    <ReferenceLine y={0} stroke="#42506a" />
    <Tooltip contentStyle={tooltip} labelFormatter={v => xKey === 'date' ? String(v).slice(0,10) : `${v} session forecast`} formatter={v => [percent ? pct(v) : fmt(v, 4), label]} />
    <Area type="linear" dataKey={dataKey} name={label} stroke={color} fill={color} fillOpacity={area ? 0.12 : 0} strokeWidth={1.4} isAnimationActive={false} connectNulls={false} />
  </AreaChart></ResponsiveContainer></div>
}
export function Bars({ data, xKey, keys, percent = true }: { data: Row[]; xKey: string; keys: { key: string; name: string; color: string }[]; percent?: boolean }) {
  if (!data.length) return <Empty title="No stored comparison available" />
  return <div className="chart chart-small"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{ top: 10, right: 15, left: 0, bottom: 0 }}>
    <CartesianGrid stroke={grid} vertical={false} strokeDasharray="3 5" /><XAxis dataKey={xKey} tick={axis} axisLine={false} tickLine={false} />
    <YAxis tick={axis} width={55} axisLine={false} tickLine={false} tickFormatter={v => percent ? pct(v, 0) : fmt(v, 1)} />
    <Tooltip contentStyle={tooltip} cursor={{ fill: '#ffffff05' }} formatter={(v, name) => [percent ? pct(v) : fmt(v, 4), name]} />
    <ReferenceLine y={0} stroke="#42506a" />{keys.map(k => <Bar key={k.key} dataKey={k.key} name={k.name} fill={k.color} radius={[2,2,0,0]} maxBarSize={35} isAnimationActive={false} />)}
  </BarChart></ResponsiveContainer></div>
}
export function Legend({ equalWeight = true }: { equalWeight?: boolean }) { return <div className="chart-legend"><span><i style={{ background: colors.portfolio }} />Portfolio</span><span><i style={{ background: colors.spy }} />SPY</span>{equalWeight && <span><i style={{ background: colors.equal_weight }} />Equal weight</span>}</div> }
