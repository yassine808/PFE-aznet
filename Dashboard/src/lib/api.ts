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

/** Mirrors the pipeline_logs row shape returned by GET /logs. */
export interface LogEntry {
  id: number
  ts: string
  stage: string
  level: string
  channel?: string | null
  technicien?: string | null
  correlation_id?: string | null
  message?: string | null
  duration_ms?: number | null
  payload?: unknown
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
  const pattern = import.meta.env.VITE_N8N_WORKFLOW_MATCH || 'r[ée]ception|pipeline complet'
  let matches: (w: N8nWorkflow) => boolean
  try {
    const re = new RegExp(pattern, 'i')
    matches = (w) => re.test(w.name)
  } catch {
    // A malformed pattern in .env must not take the status pill down with it.
    matches = (w) => /r[ée]ception|pipeline complet/i.test(w.name)
  }
  const live = workflows.filter((w) => !w.isArchived)
  return live.find((w) => w.active && matches(w)) ?? live.find(matches) ?? live.find((w) => w.active) ?? live[0]
}

export interface N8nExecution {
  id: number
  status: string
  startedAt: string
  stoppedAt?: string | null
  workflowId?: string
}

/** Last executions, newest first. Proves the orchestrator is doing work, not just running. */
export async function n8nExecutions(signal?: AbortSignal): Promise<N8nExecution[]> {
  try {
    const res = await fetch('/n8n/api/v1/executions?limit=20', { signal })
    if (!res.ok) return []
    const body = (await res.json()) as { data?: N8nExecution[] }
    return body.data ?? []
  } catch {
    return []
  }
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

/** Writes one cell back to the Sheet. Row is the 1-based Sheet row; row 1 is the header. */
export async function patchReport(row: number, field: string, value: string): Promise<void> {
  const res = await fetch(`${BASE}/reports/${row}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ field, value }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${body.slice(0, 200) || res.statusText}`)
  }
}

export interface DailyReportContent {
  objet: string
  corps: string
}

/**
 * Generates the end-of-day manager email. This is a real LLM call against a
 * free-tier quota, so it is only ever fired by an explicit user action, never
 * by a poll or on mount.
 */
export async function generateDailyReport(date: string, rows: ReportRow[]): Promise<DailyReportContent> {
  const res = await fetch(`${BASE}/daily-report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date, rows }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${body.slice(0, 300) || res.statusText}`)
  }
  return res.json() as Promise<DailyReportContent>
}

export interface Technician {
  id: number
  channel: 'telegram' | 'whatsapp'
  external_id: string
  name: string
  role?: string | null
  active: boolean
  created_at?: string
}

export async function addTechnician(input: {
  channel: string
  external_id: string
  name: string
  role?: string
}): Promise<Technician> {
  const res = await fetch(`${BASE}/technicians`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${body.slice(0, 200) || res.statusText}`)
  }
  return res.json() as Promise<Technician>
}

export async function deleteTechnician(id: number): Promise<void> {
  const res = await fetch(`${BASE}/technicians/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
}

export interface ServiceSample {
  service: string
  state: string
  ts: string
}

/** Fire-and-forget: a dropped sample is a gap in history, never a user-facing error. */
export async function postSamples(samples: { service: string; state: string }[]): Promise<void> {
  if (samples.length === 0) return
  try {
    await fetch(`${BASE}/service-samples`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ samples }),
    })
  } catch {
    /* offline: the next minute's sample will land instead */
  }
}

export const api = {
  health: (s?: AbortSignal) => get<Health>('/health', s),
  technicians: (s?: AbortSignal) => get<{ technicians: Technician[] }>('/technicians', s),
  samples: (s?: AbortSignal) => get<{ samples: ServiceSample[] }>('/service-samples?hours=2', s),
  n8n: n8nStatus,
  n8nExecutions,
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
 * Module-level response cache, keyed by endpoint.
 *
 * Without this, navigating away from a route unmounts its hooks and coming back
 * re-runs every fetch from a blank loading state, so the app appears to forget
 * everything it just showed. With it, a remount paints cached data immediately
 * and revalidates in the background: stale-while-revalidate.
 *
 * ponytail: a plain Map, not TanStack Query. Five endpoints, one consumer app,
 * no mutations to invalidate. Reach for a real query library if that changes.
 */
const cache = new Map<string, unknown>()

/**
 * Fetch on mount, optionally re-fetch on an interval.
 * Errors are kept and shown; they are never swallowed into an empty state,
 * because "no data" and "the API is down" must not look the same.
 */
export function useApi<T>(key: string, fetcher: (s?: AbortSignal) => Promise<T>, pollMs?: number): Async<T> {
  const cached = cache.get(key) as T | undefined
  const [data, setData] = useState<T | null>(cached ?? null)
  const [error, setError] = useState<string | null>(null)
  // Only the very first visit shows a skeleton; later remounts paint from cache.
  const [loading, setLoading] = useState(cached === undefined)
  const [nonce, setNonce] = useState(0)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined

    const run = async (first: boolean) => {
      if (first && cache.get(key) === undefined) setLoading(true)
      try {
        const next = await fetcherRef.current(controller.signal)
        cache.set(key, next)
        setData(next)
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
  }, [key, pollMs, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { data, error, loading, reload }
}
