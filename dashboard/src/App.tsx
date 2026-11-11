import { useEffect, useState } from 'react'
import { Activity, BookOpen, ChartNoAxesCombined, ChevronDown, ChevronRight, CircleHelp, Database, FlaskConical, GitBranch, LayoutDashboard, Menu, Radio, Settings2, ShieldCheck, SlidersHorizontal, Waypoints, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Badge, Failure, Loading, Note, PageHeader } from './components/shared'
import { Card, CardHeader } from './components/ui/card'
import { Button } from './components/ui/button'
import { cn, label, useApi } from './lib'
import type { Context, Filters, Period, Strategy } from './types'
import { Overview } from './pages/overview'
import { Universe } from './pages/universe'
import { Signals } from './pages/signals'
import { Backtests } from './pages/backtests'
import { Reports } from './pages/reports'
import { Runs } from './pages/runs'

const nav: {id:string; title:string; icon:LucideIcon; group:string; planned?:boolean}[] = [
  {id:'overview',title:'Overview',icon:LayoutDashboard,group:'WORKSPACE'},
  {id:'universe',title:'Data & universe',icon:Database,group:'WORKSPACE'},
  {id:'features',title:'Feature explorer',icon:Waypoints,group:'RESEARCH',planned:true},
  {id:'signals',title:'Signal research',icon:Activity,group:'RESEARCH'},
  {id:'validation',title:'Alpha validation',icon:FlaskConical,group:'RESEARCH',planned:true},
  {id:'backtests',title:'Backtest results',icon:ChartNoAxesCombined,group:'RESEARCH'},
  {id:'risk',title:'Portfolio & risk',icon:ShieldCheck,group:'RESEARCH',planned:true},
  {id:'robustness',title:'Robustness analysis',icon:SlidersHorizontal,group:'RESEARCH',planned:true},
  {id:'runs',title:'Runs & configuration',icon:GitBranch,group:'OPERATIONS'},
  {id:'reports',title:'Reports & audit',icon:BookOpen,group:'OPERATIONS'},
  {id:'prospective',title:'Prospective monitor',icon:Radio,group:'OPERATIONS',planned:true},
]
function initialFilters(): Filters {
  const params = new URLSearchParams(location.search)
  return {run_id:params.get('run') || 'historical',strategy:(params.get('strategy') || 'primary') as Strategy,period:(params.get('period') || 'FULL') as Period,start:params.get('start') || '',end:params.get('end') || ''}
}
export default function App() {
  const context = useApi<Context>('/context', 10000)
  const [page,setPage] = useState(location.hash.slice(1) || 'overview')
  const [filters,setFilters] = useState<Filters>(initialFilters)
  const [sidebar,setSidebar] = useState(false)
  const [showDates,setShowDates] = useState(false)
  const [help,setHelp] = useState(false)
  const [dates,setDates] = useState({start:filters.start,end:filters.end})
  useEffect(() => { const change = () => setPage(location.hash.slice(1) || 'overview');window.addEventListener('hashchange',change);return () => window.removeEventListener('hashchange',change) },[])
  useEffect(() => { const url = new URL(location.href);for (const [k,v] of Object.entries(filters)) { const key=k === 'run_id' ? 'run':k;if(v) url.searchParams.set(key,v);else url.searchParams.delete(key) }history.replaceState(null,'',url) },[filters])
  function navigate(id:string) {location.hash=id;setSidebar(false);window.scrollTo({top:0,behavior:'instant'})}
  function update(values:Partial<Filters>) {setFilters(f => ({...f,...values}))}
  const current = nav.find(item => item.id === page) || nav[0]
  const contextKey = [filters.run_id,filters.period,filters.start,filters.end].join('|')
  return <div className="app-shell">
    {sidebar && <button className="sidebar-overlay" aria-label="Close navigation" onClick={() => setSidebar(false)} />}
    <aside className={cn('sidebar',sidebar && 'sidebar-open')}>
      <a className="brand" href="#overview" aria-label="Axiom overview"><span className="brand-mark">Σ</span><span>AXIOM<small>QUANTITATIVE RESEARCH</small></span></a>
      <div className="workspace-picker"><span className="workspace-icon"><ChartNoAxesCombined size={16} /></span><div><strong>Equity research</strong><span>Systematic strategies</span></div><ChevronDown size={13} /></div>
      <nav aria-label="Main navigation">{['WORKSPACE','RESEARCH','OPERATIONS'].map(group => <div className="nav-group" key={group}><div className="nav-group-label">{group}</div>{nav.filter(item => item.group === group).map(item => <a href={`#${item.id}`} onClick={() => setSidebar(false)} className={cn('nav-item',current.id === item.id && 'active',item.planned && 'planned')} key={item.id} aria-current={current.id === item.id ? 'page':undefined}><item.icon size={17} /><span>{item.title}</span>{item.planned ? <span className="planned-dot" title="Planned module" /> : current.id === item.id ? <ChevronRight size={13} /> : null}</a>)}</div>)}</nav>
      <div className="sidebar-bottom"><div className="environment"><span className="connection-dot" /><strong>LOCAL RESEARCH</strong><span>v1.0</span></div><p>Evidence before conviction.</p><button onClick={() => setHelp(!help)}><CircleHelp size={15} />Workspace guide<ChevronRight size={13} /></button><div className="user-profile"><span>QR</span><div><strong>Research workspace</strong><small>Local repository</small></div><Settings2 size={15} /></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><Button variant="ghost" size="icon" className="mobile-menu" aria-label="Open navigation" onClick={() => setSidebar(!sidebar)}><Menu size={19} /></Button><span className="muted">Workspace</span><ChevronRight size={13} /><strong>{current.title}</strong></div><div className="topbar-right"><span className="connection-state"><span className={cn('connection-dot',context.error && 'offline')} />{context.loading ? 'Connecting':context.error ? 'API unavailable':'Local API connected'}</span><span className="top-divider" /><Badge>RESEARCH ONLY</Badge><button className="help-button" aria-label="Workspace guide" onClick={() => setHelp(!help)}><CircleHelp size={17} /></button></div></header>
    <div className="context-bar"><div className="context-picker"><GitBranch size={14} /><label>Context<select aria-label="Research run" value={filters.run_id} onChange={e => update({run_id:e.target.value})}>{context.data?.runs.map(run => <option value={run.id} key={run.id}>{run.label}{run.status !== 'historical' ? ` · ${run.id.slice(0,8)} · ${run.status}`:''}</option>)}</select></label></div><div className="context-picker"><ChartNoAxesCombined size={14} /><label>Strategy<select aria-label="Strategy" value={filters.strategy} onChange={e => update({strategy:e.target.value as Strategy})}><option value="primary">Primary · sector-neutral momentum</option><option value="challenger">Challenger · momentum + volatility</option><option value="raw_momentum_benchmark">Raw momentum benchmark</option></select></label></div><div className="context-picker period-picker"><label>Sample<select aria-label="Research period" value={filters.period} onChange={e => update({period:e.target.value as Period})}><option value="FULL">Full history</option><option value="DEVELOPMENT">Development · through 2021</option><option value="CONFIRMATION">Confirmation · 2022 onward</option></select></label></div><button className={cn('date-filter',showDates && 'selected')} onClick={() => setShowDates(!showDates)}><SlidersHorizontal size={14} />{filters.start || filters.end ? 'Custom dates':'Date range'}<ChevronDown size={12} /></button></div>
    {showDates && <form className="date-range-panel" onSubmit={e => {e.preventDefault();update(dates);setShowDates(false)}}><label>From<input aria-label="Start date" type="date" value={dates.start} onChange={e => setDates(d => ({...d,start:e.target.value}))} /></label><span>→</span><label>Through<input aria-label="End date" type="date" value={dates.end} onChange={e => setDates(d => ({...d,end:e.target.value}))} /></label><Button type="submit" variant="default" disabled={!!dates.start && !!dates.end && dates.start > dates.end}>Apply dates</Button><Button type="button" onClick={() => {setDates({start:'',end:''});update({start:'',end:''});setShowDates(false)}}>Reset</Button><small>Charts use these dates. Stored signal inference retains its original sample.</small></form>}
    <main>
      {help && <Card className="workspace-guide"><CardHeader title="Workspace guide" action={<Button size="icon" variant="ghost" aria-label="Close guide" onClick={() => setHelp(false)}><X size={16} /></Button>} /><p>Browse saved repository artifacts without rerunning experiments. Context selects the artifact set; strategy and sample update historical performance. Data & universe supports ticker, sector, and liquidity filters. Reports retain original files. Runs execute fixed existing stages into separate directories.</p><Note>Planned modules have a small dot in navigation. The API reference is available at <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">localhost:8000/docs</a>.</Note></Card>}
      {context.loading ? <Loading /> : context.error ? <Failure message={context.error} retry={context.refresh} /> : current.planned ? <><PageHeader eyebrow="ROADMAP" title={current.title} description="Reserved for a later phase of the research workspace." /><Card><CardHeader title={current.id === 'prospective' ? 'Prospective monitoring unavailable':'This module is planned'} subtitle="Existing research outputs remain available in Reports & audit." /><div className="planned-content"><current.icon size={35} /><h2>{current.id === 'prospective' ? label(context.data?.prospective.status || 'Provider integration unavailable'):'An evidence-backed extension'}</h2><p>{current.id === 'prospective' ? 'Provider and account integrations are unavailable. Historical simulations remain separate from future prospective records.':'The MVP focuses on reliable artifact browsing and research execution. This view will be added using the existing engine and recorded outputs.'}</p><Button onClick={() => navigate('reports')}>Browse source artifacts</Button></div></Card></> : <div key={contextKey}>
      {current.id === 'overview' && <Overview filters={filters} navigate={navigate} />}
      {current.id === 'universe' && <Universe filters={filters} navigate={navigate} />}
      {current.id === 'signals' && <Signals filters={filters} />}
      {current.id === 'backtests' && <Backtests filters={filters} />}
      {current.id === 'reports' && <Reports filters={filters} />}
      {current.id === 'runs' && <Runs filters={filters} onLaunched={context.refresh} />}
      </div>}
    </main><footer className="app-footer"><span>AXIOM <span className="muted">/</span> Quantitative research platform</span><span>Historical simulation ≠ live performance</span></footer></div>
  </div>
}
