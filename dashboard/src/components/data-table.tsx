import { useState } from 'react'
import { flexRender, getCoreRowModel, getFilteredRowModel, getPaginationRowModel, getSortedRowModel, useReactTable, type ColumnDef, type SortingState, type OnChangeFn } from '@tanstack/react-table'
import { ArrowDown, ArrowUp, ChevronsUpDown, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { Button } from './ui/button'
import { Empty } from './shared'

export function DataTable<T>({ data, columns, searchPlaceholder, pageSize = 10, onRowClick, sorting: externalSorting, onSortingChange,
  serverPage, total, onPageChange }: {
  data: T[]; columns: ColumnDef<T>[]; searchPlaceholder?: string; pageSize?: number; onRowClick?: (row: T) => void
  sorting?: SortingState; onSortingChange?: OnChangeFn<SortingState>; serverPage?: number; total?: number; onPageChange?: (page: number) => void
}) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [search, setSearch] = useState('')
  const table = useReactTable({ data, columns, state: { sorting: externalSorting ?? sorting, globalFilter: search },
    onSortingChange: onSortingChange ?? setSorting, onGlobalFilterChange: setSearch,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(), getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(), manualSorting: !!onSortingChange, manualPagination: !!onPageChange,
    initialState: { pagination: { pageSize } },
  })
  const count = total ?? table.getFilteredRowModel().rows.length
  const page = serverPage ?? table.getState().pagination.pageIndex + 1
  return <div className="data-table">
    {searchPlaceholder && <div className="table-toolbar"><label className="search-field"><Search size={15} /><input aria-label={searchPlaceholder} placeholder={searchPlaceholder} value={search} onChange={e => { setSearch(e.target.value); table.setPageIndex(0) }} /></label></div>}
    <div className="table-scroll"><table><thead>{table.getHeaderGroups().map(group => <tr key={group.id}>{group.headers.map(header => <th key={header.id}>
      <button className="column-heading" onClick={header.column.getToggleSortingHandler()} disabled={!header.column.getCanSort()}>
        {flexRender(header.column.columnDef.header, header.getContext())}
        {header.column.getCanSort() && (header.column.getIsSorted() === 'asc' ? <ArrowUp size={11} /> : header.column.getIsSorted() === 'desc' ? <ArrowDown size={11} /> : <ChevronsUpDown size={11} className="muted" />)}
      </button></th>)}</tr>)}</thead><tbody>{table.getRowModel().rows.map(row => <tr key={row.id} className={onRowClick ? 'clickable-row' : ''} onClick={() => onRowClick?.(row.original)} tabIndex={onRowClick ? 0 : undefined} onKeyDown={e => { if (onRowClick && e.key === 'Enter') onRowClick(row.original) }}>
        {row.getVisibleCells().map(cell => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}
      </tr>)}</tbody></table>{!data.length && <Empty title="No matching records" description="Adjust the filters or choose another run." />}</div>
    <div className="table-footer"><span>{count ? `${(page-1)*pageSize+1}–${Math.min(page*pageSize, count)}` : '0'} of {count.toLocaleString()} records</span><div><Button size="icon" aria-label="Previous page" disabled={page <= 1} onClick={() => onPageChange ? onPageChange(page-1) : table.previousPage()}><ChevronLeft size={15} /></Button><span>Page {page} of {Math.max(1, Math.ceil(count / pageSize))}</span><Button size="icon" aria-label="Next page" disabled={page*pageSize >= count} onClick={() => onPageChange ? onPageChange(page+1) : table.nextPage()}><ChevronRight size={15} /></Button></div></div>
  </div>
}
