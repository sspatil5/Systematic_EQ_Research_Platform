import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DataTable } from './data-table'
import { Metrics, Failure } from './shared'
import { fmt, pct, useApi } from '../lib'

afterEach(() => vi.unstubAllGlobals())
describe('research table', () => {
  it('filters, sorts, and paginates actual supplied rows', () => {
    const rows = [{ticker:'SPY',count:2},{ticker:'AAPL',count:3},{ticker:'MSFT',count:1}]
    render(<DataTable data={rows} columns={[{accessorKey:'ticker',header:'Ticker'},{accessorKey:'count',header:'Count'}]} searchPlaceholder="Search test rows" pageSize={2} />)
    expect(screen.getByText('SPY')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Ticker'}))
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.queryByText('SPY')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Next page'}))
    expect(screen.getByText('SPY')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox'),{target:{value:'ms'}})
    expect(screen.getByText('MSFT')).toBeInTheDocument()
    expect(screen.queryByText('SPY')).not.toBeInTheDocument()
  })
  it('renders an explicit empty result', () => {
    render(<DataTable data={[]} columns={[{accessorKey:'ticker',header:'Ticker'}]} />)
    expect(screen.getByText('No matching records')).toBeInTheDocument()
  })
})
describe('metric fidelity and failure states', () => {
  it('keeps missing metrics unavailable', () => {
    render(<Metrics metrics={{}} />)
    expect(screen.getAllByText('—')).toHaveLength(4)
    expect(fmt(NaN)).toBe('—')
    expect(pct(null)).toBe('—')
    expect(pct(.123456)).toBe('12.35%')
  })
  it('shows actionable API errors and permits retry', () => {
    const retry=vi.fn()
    render(<Failure message="Required panel missing" retry={retry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Required panel missing')
    fireEvent.click(screen.getByRole('button',{name:'Retry request'}))
    expect(retry).toHaveBeenCalledOnce()
  })
  it('does not let a stale filter request replace a newer result', async () => {
    let resolveFirst: (value: Response) => void = () => {}
    vi.stubGlobal('fetch',vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => {resolveFirst=resolve})).mockResolvedValueOnce({ok:true,json:async () => ({value:'new'})}))
    function View({ path }: { path:string }) { const result=useApi<{value:string}>(path);return <div>{result.data?.value || 'loading'}</div> }
    const view=render(<View path="/old" />)
    view.rerender(<View path="/new" />)
    await waitFor(() => expect(screen.getByText('new')).toBeInTheDocument())
    resolveFirst({ok:true,json:async () => ({value:'old'})} as Response)
    await waitFor(() => expect(screen.queryByText('old')).not.toBeInTheDocument())
  })
})
