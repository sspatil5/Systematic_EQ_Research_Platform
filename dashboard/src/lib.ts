import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { useCallback, useEffect, useState } from 'react'

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs))
export function number(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
export function fmt(value: unknown, digits = 2) {
  const n = number(value)
  return n === null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}
export function pct(value: unknown, digits = 2) {
  const n = number(value)
  return n === null ? '—' : `${fmt(n * 100, digits)}%`
}
export function money(value: unknown, compact = false) {
  const n = number(value)
  return n === null ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: compact ? 'compact' : 'standard', maximumFractionDigits: compact ? 1 : 0 }).format(n)
}
export const label = (value: unknown) => String(value ?? '').replaceAll('_', ' ')
export const shortDate = (value: unknown) => value ? String(value).slice(0, 10) : 'Not recorded'
export function timestamp(value: string | null) {
  return value ? new Date(value).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'America/New_York' }) + ' ET' : 'Not recorded'
}
export const size = (bytes: number) => bytes >= 1048576 ? `${fmt(bytes / 1048576, 1)} MB` : `${fmt(bytes / 1024, 1)} KB`

export function query(values: object) {
  return new URLSearchParams(Object.entries(values).filter(([, v]) => v !== '' && v !== null && v !== undefined).map(([k, v]) => [k, String(v)])).toString()
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, options)
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `Request failed (${response.status}). Check that the local API is running.`)
  }
  return response.json()
}
export function useApi<T>(path: string | null, poll = 0) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true })
  const [version, setVersion] = useState(0)
  const refresh = useCallback(() => setVersion(v => v + 1), [])
  useEffect(() => {
    if (!path) { setState({ loading: false }); return }
    let active = true
    let timer: ReturnType<typeof setTimeout>
    const controller = new AbortController()
    setState({ loading: true })
    async function load() {
      try {
        const data = await api<T>(path!, { signal: controller.signal })
        if (active) setState({ data, loading: false })
      } catch (error) {
        if (active) setState({ error: (error as Error).message, loading: false })
      }
      if (active && poll) timer = setTimeout(load, poll)
    }
    void load()
    return () => { active = false; controller.abort(); clearTimeout(timer) }
  }, [path, poll, version])
  return { ...state, refresh }
}

export function exportCsv(rows: Record<string, unknown>[], filename: string) {
  if (!rows.length) return
  const columns = Object.keys(rows[0])
  const escape = (value: unknown) => {
    let text = String(value ?? '')
    if (/^[=+@\-\t\r]/.test(text) && typeof value !== 'number') text = `'${text}`
    return `"${text.replaceAll('"', '""')}"`
  }
  const content = [columns, ...rows.map(row => columns.map(k => row[k]))].map(row => row.map(escape).join(',')).join('\r\n')
  const url = URL.createObjectURL(new Blob([content], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
