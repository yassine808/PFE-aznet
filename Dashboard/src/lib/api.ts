import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Vite proxies /api to the FastAPI service (see vite.config.ts), so the browser
 * stays same-origin and the API needs no CORS configuration.
 */
const BASE = '/api'

/** One row of the `Rapports` tab. Sheets returns every cell as a string. */
export interface ReportRow {
  _row: number
  date?: string
  heure?: string
  canal?: string
  technicien?: string
  role?: string
  chantier?: string
  client?: string
  type_activite?: string
  goulottes_m?: string
  cables_m?: string
  bureaux_termines?: string
  panneaux_raccordes?: string
  autres_travaux?: string
  observations?: string
  resume?: string
  rapport_complet?: string
  confidence?: string
  flag_review?: string
  lien_audio?: string
}

export interface Health {
  status: string
  version: string
  uptime_seconds: number
  started_at: number
  stt_providers: string[]
  stt_default: string
}

export interface LogEntry {
  id: number
  ts: string
  stage: string
  level: string
  channel?: string | null
  correlation_id?: string | null
  message?: string | null
  detail?: unknown
}

export interface LogStats {
  last_24h: Record<string, number>
  pending_sheet_writes: number
  retention_days: number
}

export interface PendingWrite {
  id: number
  payload: Record<string, unknown>
  error: string
  correlation_id?: string | null
  created_at?: string
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { signal })
  if (!res.ok) {
    // Surface the API's own message: "sheets read failed: ..." is far more
    // actionable to the operator than a bare 502.
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${body.slice(0, 200) || res.statusText}`)
  }
  return res.json() as Promise<T>
}

export interface N8nWorkflow {
  id: string
  name: string
  active: boolean
  isArchived?: boolean
}

/**
 * Picks the workflow whose state the nav pill reports.
 *
 * This instance holds a dozen archived duplicates named "Reception unified ...",
 * all inactive, alongside the live "aznet — pipeline complet ..." workflow.
 * Taking the first name match would report the pipeline as disabled while it is
 * running, so: ignore archived, prefer an active reception workflow, and only
 * then fall back to a name match.
 */
export function pickReceptionWorkflow(workflows: N8nWorkflow[]): N8nWorkflow | undefined {
  const live = workflows.filter((w) => !w.isArchived)
  const matches = (w: N8nWorkflow) => /r[ée]ception|pipeline complet/i.test(w.name)
  return live.find((w) => w.active && matches(w)) ?? live.find(matches) ?? live.find((w) => w.active) ?? live[0]
}

/**
 * n8n's public API, reached through the dev proxy which attaches the API key.
 * A reachable server with every workflow deactivated is a real and dangerous
 * state, so server health and workflow activation are reported separately.
 */
export async function n8nStatus(
  signal?: AbortSignal,
): Promise<{ reachable: boolean; workflows: N8nWorkflow[]; authError: boolean }> {
  try {
    const res = await fetch('/n8n/api/v1/workflows', { signal })
    if (res.status === 401 || res.status === 403) return { reachable: true, workflows: [], authError: true }
    if (!res.ok) return { reachable: true, workflows: [], authError: false }
    const body = (await res.json()) as { data?: N8nWorkflow[] }
    return { reachable: true, workflows: body.data ?? [], authError: false }
  } catch {
    // Connection refused: n8n is not running. Not an app error, a reported state.
    return { reachable: false, workflows: [], authError: false }
  }
}

export const api = {
  health: (s?: AbortSignal) => get<Health>('/health', s),
  n8n: n8nStatus,
  reports: (s?: AbortSignal) => get<{ reports: ReportRow[] }>('/reports', s),
  logs: (s?: AbortSignal) => get<{ logs: LogEntry[]; stats: LogStats }>('/logs?limit=50', s),
  queue: (s?: AbortSignal) => get<{ pending: PendingWrite[] }>('/sheet-queue', s),
}

export interface Async<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/**
 * Fetch on mount, optionally re-fetch on an interval.
 * Errors are kept and shown; they are never swallowed into an empty state,
 * because "no data" and "the API is down" must not look the same.
 */
export function useApi<T>(fetcher: (s?: AbortSignal) => Promise<T>, pollMs?: number): Async<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [nonce, setNonce] = useState(0)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined

    const run = async (first: boolean) => {
      if (first) setLoading(true)
      try {
        setData(await fetcherRef.current(controller.signal))
        setError(null)
      } catch (err) {
        if (controller.signal.aborted) return
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }

    void run(true)
    if (pollMs) timer = window.setInterval(() => void run(false), pollMs)

    return () => {
      controller.abort()
      if (timer) window.clearInterval(timer)
    }
  }, [pollMs, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { data, error, loading, reload }
}
