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
  last_error: string
  correlation_id?: string | null
  created_at?: string
  attempts?: number
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { signal })
  if (!res.ok) await fail(res)
  return res.json() as Promise<T>
}

export interface N8nNode {
  id: string
  name: string
  type: string
  /** Canvas coordinates as stored by n8n: [x, y]. */
  position: [number, number]
  disabled?: boolean
  parameters?: Record<string, unknown>
}

/**
 * n8n's connection map: source node name -> output kind -> output index ->
 * list of targets. The double array is not a typo: index 0 is the first
 * output, and an IF node has two.
 */
export type N8nConnections = Record<
  string,
  Record<string, { node: string; type: string; index: number }[][]>
>

export interface N8nWorkflow {
  id: string
  name: string
  active: boolean
  isArchived?: boolean
  updatedAt?: string
  nodes?: N8nNode[]
  connections?: N8nConnections
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
  return (
    live.find((w) => w.active && matches(w)) ??
    live.find(matches) ??
    live.find((w) => w.active) ??
    live[0]
  )
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
    const res = await fetch(`${BASE}/n8n/executions?limit=20`, { signal })
    if (!res.ok) return []
    const body = (await res.json()) as { data?: N8nExecution[] }
    return body.data ?? []
  } catch {
    return []
  }
}

/**
 * n8n's public API, reached through the API (GET /n8n/workflows) which attaches
 * the key server-side and gates the route behind a session. A reachable server
 * with every workflow deactivated is a real and dangerous state, so server
 * health and workflow activation are reported separately.
 */
export async function n8nStatus(
  signal?: AbortSignal,
): Promise<{ reachable: boolean; workflows: N8nWorkflow[]; authError: boolean }> {
  try {
    const res = await fetch(`${BASE}/n8n/workflows`, { signal })
    // The API collapses every n8n-side failure into 502; the detail says which.
    // "rejected" means n8n answered and refused the key — the server is up.
    if (res.status === 502) {
      const detail = await res.text().catch(() => '')
      return {
        reachable: /rejected/.test(detail),
        workflows: [],
        authError: /rejected/.test(detail),
      }
    }
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
  if (!res.ok) await fail(res)
}

/** Outbound manager reply, sent by the API on the technician's own channels. */
export interface ReplyResult {
  delivered: { channel: string }[]
}

export async function sendReply(name: string, text: string): Promise<ReplyResult> {
  const res = await fetch(`${BASE}/reply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, text }),
  })
  if (!res.ok) await fail(res)
  return (await res.json()) as ReplyResult
}

/**
 * One stored generated report: the same text the scheduler mailed and the
 * /rapport command answers with — per site manager, per period.
 */
export interface GeneratedReport {
  manager_id: number
  manager_name: string
  period: string
  period_type: 'daily' | 'weekly'
  objet: string
  corps: string
  generated_at: string
  generated_by: string
}

/** An illustrated summary card, returned as a data URI — never written to the Sheet. */
export interface GeneratedImage {
  model: string
  mime_type: string
  data_uri: string
}

/**
 * Renders the summary card for a period. A real image-model call against a
 * metered free tier: fired alongside the report's own "Générer" gesture
 * (daily/weekly pages), never by a poll.
 */
export async function generateImage(rows: ReportRow[], title: string): Promise<GeneratedImage> {
  const res = await fetch(`${BASE}/generate-image`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows, title }),
  })
  if (!res.ok) await fail(res)
  return res.json() as Promise<GeneratedImage>
}

export interface DailyReportContent {
  objet: string
  corps: string
  /** Who asked for the report — an account name, or "automatique" for the scheduled mail. */
  generated_by?: string
}

/**
 * Generates the end-of-day manager email. This is a real LLM call against a
 * free-tier quota, so it is only ever fired by an explicit user action, never
 * by a poll or on mount.
 */
export async function generateDailyReport(
  date: string,
  rows: ReportRow[],
): Promise<DailyReportContent> {
  const res = await fetch(`${BASE}/daily-report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date, rows }),
  })
  if (!res.ok) await fail(res)
  return res.json() as Promise<DailyReportContent>
}

/** One channel handle. Several of these can belong to the same person. */
export interface Identity {
  id: number
  person_id: number
  channel: 'telegram' | 'whatsapp'
  external_id: string
  active: boolean
  created_at?: string
}

/**
 * A colleague, with every channel they write from. `GET /technicians` returns
 * people — the endpoint kept its name because the workflow calls it too, and
 * renaming a working URL to match an internal refactor buys nothing.
 */
export interface Technician {
  id: number
  name: string
  role?: string | null
  /** Which chef they report to. Null = the chart's unassigned column. */
  manager_id?: number | null
  email?: string | null
  /** Derived server-side from `password_hash IS NOT NULL` — the hash never ships. */
  has_login?: boolean
  active?: boolean
  last_seen_at?: string | null
  /** Nightly summary written by the profile model. Null until the first run. */
  profile?: string | null
  profile_updated_at?: string | null
  identities: Identity[]
  created_at?: string
}

/**
 * One saved state of an edited report.
 *
 * The index call omits `corps` and `image`, so a version list costs a few
 * hundred bytes rather than every stored document; ask for `full` only when an
 * old version is actually opened.
 */
export interface ReportVersion {
  id: number
  kind: 'daily' | 'weekly'
  period: string
  version: number
  objet: string
  corps?: string
  image?: string | null
  author: string
  note?: string | null
  created_at: string
}

export const reportVersions = (
  kind: 'daily' | 'weekly',
  period: string,
  full = false,
  signal?: AbortSignal,
) =>
  get<{ versions: ReportVersion[] }>(
    `/report-versions?kind=${kind}&period=${encodeURIComponent(period)}&full=${full}`,
    signal,
  )

export const saveReportVersion = (input: {
  kind: 'daily' | 'weekly'
  period: string
  objet: string
  corps: string
  image?: string | null
  note?: string | null
}) => post<ReportVersion>('/report-versions', input)

/** The org chart's "+": a chef with no channel and no login yet. */
export const addPerson = (input: { name: string; role?: string }) =>
  post<{ id: number; name: string; role: string }>('/persons', input)

/** Reassign to a chef, or to nobody with null. One PATCH per drop. */
export async function setManager(id: number, managerId: number | null): Promise<void> {
  const res = await fetch(`${BASE}/persons/${id}/manager`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ manager_id: managerId }),
  })
  if (!res.ok) await fail(res)
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
  if (!res.ok) await fail(res)
  return res.json() as Promise<Technician>
}

/** Remove one channel handle. The person and their profile survive. */
export async function deleteTechnician(id: number): Promise<void> {
  const res = await fetch(`${BASE}/technicians/${id}`, { method: 'DELETE' })
  if (!res.ok) await fail(res)
}

/** Remove the person and every handle they own. */
export async function deletePerson(id: number): Promise<void> {
  const res = await fetch(`${BASE}/persons/${id}`, { method: 'DELETE' })
  if (!res.ok) await fail(res)
}

/**
 * Rebuild one profile now instead of waiting for the 03:00 cron. Slow by
 * nature — it is a model call — so callers must show a pending state.
 */
export async function refreshProfile(id: number): Promise<{ updated: boolean; reason?: string }> {
  const res = await fetch(`${BASE}/persons/${id}/profile`, { method: 'POST' })
  if (!res.ok) await fail(res)
  return res.json() as Promise<{ updated: boolean; reason?: string }>
}

/**
 * Scheduled maintenance jobs, run by the API's own scheduler.
 *
 * `last` is null until a job has run at least once in the current API process:
 * the status is in-memory, so a restart empties it. That is deliberate — the
 * durable record of every run is in the pipeline logs, and persisting a second
 * copy here would be a cache with nothing to gain from it.
 */
export interface JobStatus {
  name: string
  schedule: string
  last: {
    ok: boolean
    at: string
    seconds: number
    result?: Record<string, unknown>
    error?: string
  } | null
}

/**
 * Force one job now. Resolves even when the job itself failed — `ok: false`
 * carries the reason, and a rejected promise would make a Sheets quota error
 * look like the dashboard being broken.
 */
export async function runJob(name: string): Promise<JobStatus['last']> {
  const res = await fetch(`${BASE}/jobs/${name}/run`, { method: 'POST' })
  if (!res.ok) await fail(res)
  return res.json() as Promise<JobStatus['last']>
}

/** Drop a queued write after a human confirms it's a dead letter, not a Sheets blip. */
export async function dismissQueueItem(id: number): Promise<void> {
  const res = await fetch(`${BASE}/sheet-queue/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ok: true }),
  })
  if (!res.ok) await fail(res)
}

/** Operator preferences, stored server-side so any scheduler reads the same values. */
export interface AppSettings {
  daily_time?: string
  weekly_day?: number
  weekly_time?: string
  emails?: string[]
  /** Ordre des moteurs STT, ex. `groq,gemini,local`. Écriture directeur
   *  uniquement — l'API renvoie 403 sinon, et 422 sur un moteur inconnu. */
  stt_chain?: string
}

/** GET /stt/status — moteurs, ordre en vigueur, et usage réel. */
export interface SttStatus {
  available: string[]
  chain: string[]
  /** Ordre par défaut (.env), pour le bouton de réinitialisation. */
  default_chain: string[]
  usage: {
    days: number
    error: string | null
    engines: { engine: string; today: number; period: number }[]
  }
  local: { url_set: boolean; status: string }
  quota_reporting: Record<string, string>
}

/** This account's dashboard preferences, stored per person in the database.
 *  Loose on purpose: the browser owns the shape and merges this over its own
 *  defaults, so the API never needs to know about a new preference. */
export interface MeSettings {
  refreshMs?: number
  confidence?: number
  density?: string
  timeFormat?: string
}

export const meSettings = (s?: AbortSignal) =>
  get<{ settings: Partial<MeSettings> }>('/me/settings', s)

export async function putMeSettings(values: Partial<MeSettings>): Promise<Partial<MeSettings>> {
  const res = await fetch(`${BASE}/me/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values }),
  })
  if (!res.ok) await fail(res)
  return ((await res.json()) as { settings: Partial<MeSettings> }).settings
}

export async function putSettings(values: Partial<AppSettings>): Promise<AppSettings> {
  const res = await fetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values }),
  })
  if (!res.ok) await fail(res)
  return ((await res.json()) as { settings: AppSettings }).settings
}

export async function sendTestMail(to: string): Promise<void> {
  const res = await fetch(`${BASE}/notify/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to }),
  })
  if (!res.ok) await fail(res) // the API names the missing env vars on a 422
}

// ── Accounts, sessions and history ────────────────────────────────────────
// The session cookie is httpOnly, so nothing here ever touches the token. The
// Vite proxy keeps /api same-origin, which is what makes the cookie ride along
// on every fetch without `credentials: 'include'`.

export interface Account {
  id: number
  email: string
  name: string
  role: 'directeur' | 'chef'
  active: boolean
  last_seen_at?: string | null
  created_at?: string
}

export interface UserAction {
  id: number
  user_id: number | null
  user_name: string | null
  action: string
  target?: string | null
  before_val?: string | null
  after_val?: string | null
  created_at: string
}

export interface History {
  actions: UserAction[]
  /** action name → count. The numbers are COUNT queries, not stored counters. */
  totals: Record<string, number>
  pages: { route: string; seconds: number; visits: number }[]
  daily: { day: string; n: number }[]
  total_seconds: number
}

/** Turn a non-OK response into a readable Error: our HTTPExceptions carry a
 * string detail, pydantic validation errors an array of { msg } — both must
 * end up as plain text, never "[object Object]". */
async function fail(res: Response): Promise<never> {
  const text = await res.text().catch(() => '')
  let detail = text
  try {
    const parsed = JSON.parse(text) as { detail?: string | Array<{ msg?: string }> }
    if (typeof parsed.detail === 'string') detail = parsed.detail
    else if (Array.isArray(parsed.detail)) {
      detail = parsed.detail
        .map((d) => d.msg)
        .filter(Boolean)
        .join(' ; ')
    }
  } catch {
    /* not JSON — use the raw body */
  }
  if (res.status === 401) {
    // The session died mid-use: expired, or its row was deleted (revoked). No
    // single panel can fix that — every poll would keep failing with the same
    // 401 — so tell the app to drop the user back on the login screen.
    window.dispatchEvent(new Event('aznet:unauthorized'))
  }
  throw new Error(detail.slice(0, 300) || `${res.status} ${res.statusText}`)
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) await fail(res)
  return res.json() as Promise<T>
}

export const login = (email: string, password: string) =>
  post<{ user: Account }>('/auth/login', { email, password })

export const logout = () => post<{ ok: boolean }>('/auth/logout')

/** Null when signed out. Not a 401, so it cannot be confused with the API being down. */
export const whoami = (s?: AbortSignal) => get<{ user: Account | null }>('/auth/me', s)

export const listUsers = (s?: AbortSignal) => get<{ users: Account[] }>('/users', s)

export const createUser = (input: { email: string; name: string; password: string }) =>
  post<Account>('/users', input)

export async function deleteUser(id: number): Promise<void> {
  const res = await fetch(`${BASE}/users/${id}`, { method: 'DELETE' })
  if (!res.ok) await fail(res)
}

export const history = (userId?: number, s?: AbortSignal) =>
  get<History>(userId ? `/history?user_id=${userId}` : '/history', s)

/**
 * Time spent on a page. `sendBeacon` because this fires as the tab is closing,
 * when a normal fetch is cancelled by the browser.
 */
export function trackVisit(route: string, seconds: number): void {
  if (seconds <= 0) return
  const body = JSON.stringify({ route, seconds })
  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon(`${BASE}/page-visit`, new Blob([body], { type: 'application/json' }))
      return
    }
    void fetch(`${BASE}/page-visit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
    })
  } catch {
    /* a lost visit is a gap in a graph, never a user-facing error */
  }
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

export interface NotificationItem {
  id: number
  kind: 'report' | 'review' | 'error' | 'reminder'
  title: string
  body?: string | null
  /** Dashboard hash route the bell links to, e.g. '#/reports'. */
  route?: string | null
  ref_id?: string | null
  created_at: string
  read_at?: string | null
}

export type TaskRepeat = 'none' | 'daily' | 'weekly' | 'monthly'
export type TaskUnit = 'day' | 'week' | 'month'

export interface TaskItem {
  id: number
  title: string
  notes?: string | null
  due_at?: string | null
  repeat: TaskRepeat
  remind_before_value?: number | null
  remind_before_unit?: TaskUnit | null
  repeat_every?: number | null
  repeat_unit?: TaskUnit | null
  done_at?: string | null
  created_at: string
  updated_at: string
}

export const notifications = (s?: AbortSignal) =>
  get<{ items: NotificationItem[]; unread: number }>('/notifications', s)

/** Marks the given notifications read, or all of them when `ids` is omitted. */
export const markNotificationsRead = (ids?: number[]) =>
  post<{ marked: number }>('/notifications/read', { ids: ids ?? null })

export const tasks = (s?: AbortSignal) => get<{ tasks: TaskItem[] }>('/tasks', s)

export type TaskInput = {
  title: string
  notes?: string | null
  due_at?: string | null
  repeat?: TaskRepeat
  remind_before_value?: number | null
  remind_before_unit?: TaskUnit | null
  repeat_every?: number | null
  repeat_unit?: TaskUnit | null
}

export const createTask = (input: TaskInput) =>
  post<{
    id: number
    title: string
    notes?: string | null
    due_at?: string | null
    repeat: string
    done: boolean
  }>('/tasks', input)

export async function updateTask(
  id: number,
  fields: Partial<TaskInput> & { done?: boolean },
): Promise<void> {
  const res = await fetch(`${BASE}/tasks/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })
  if (!res.ok) await fail(res)
}

export async function deleteTask(id: number): Promise<void> {
  const res = await fetch(`${BASE}/tasks/${id}`, { method: 'DELETE' })
  if (!res.ok) await fail(res)
}

export const api = {
  health: (s?: AbortSignal) => get<Health>('/health', s),
  technicians: (s?: AbortSignal) => get<{ technicians: Technician[] }>('/technicians', s),
  settings: (s?: AbortSignal) => get<{ settings: AppSettings }>('/settings', s),
  sttStatus: (s?: AbortSignal) => get<SttStatus>('/stt/status', s),
  users: listUsers,
  history,
  samples: (s?: AbortSignal) => get<{ samples: ServiceSample[] }>('/service-samples?hours=2', s),
  n8n: n8nStatus,
  n8nExecutions,
  reports: (s?: AbortSignal) => get<{ reports: ReportRow[] }>('/reports', s),
  generatedReports: (s?: AbortSignal) =>
    get<{ reports: GeneratedReport[] }>('/reports/generated', s),
  logs: (s?: AbortSignal) => get<{ logs: LogEntry[]; stats: LogStats }>('/logs?limit=50', s),
  queue: (s?: AbortSignal) => get<{ pending: PendingWrite[] }>('/sheet-queue', s),
  jobs: (s?: AbortSignal) => get<{ jobs: JobStatus[] }>('/jobs', s),
  notifications,
  tasks,
}

export interface Async<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/**
 * Module-level response cache, keyed by endpoint, with subscribers.
 *
 * Without this, navigating away from a route unmounts its hooks and coming back
 * re-runs every fetch from a blank loading state, so the app appears to forget
 * everything it just showed. With it, a remount paints cached data immediately
 * and revalidates in the background: stale-while-revalidate.
 *
 * The subscriber list makes the cache reactive: when any hook writes fresh data
 * (a poll, a remount, a reload), every other hook on the same key repaints too.
 * Without it, a page that reads a key nobody polls keeps its mount-time
 * snapshot for the whole visit — Overview's headline numbers froze until
 * navigation.
 *
 * ponytail: a Map plus a listener set, not TanStack Query. Five endpoints, one
 * consumer app, no mutations to invalidate. Reach for a real query library if
 * that changes.
 */
const cache = new Map<string, unknown>()
const listeners = new Map<string, Set<() => void>>()
// One promise per key while a request is in flight. Without it, two components
// mounting the same endpoint each fire their own fetch and their own interval —
// the cache dedupes the paint but not the request (audit 2026-08-04 #10's
// related note). The shared promise is deliberately not abortable: it outlives
// any one hook, so an unmount cannot cancel a request another mount is waiting
// on. The per-hook controller still gates the local setState afterwards.
const inflight = new Map<string, Promise<unknown>>()
// Bumped by `clearCache`. A fetch started before an account change must not
// write its response into the cache afterwards — without it, a slow request
// from the previous session's poll can land the old account's rows under the
// new one's key after the clear, and the next mount repaints them.
let generation = 0

function runDedupe<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const existing = inflight.get(key)
  if (existing) return existing as Promise<T>
  const p = fetcher().finally(() => inflight.delete(key))
  inflight.set(key, p)
  return p
}

/**
 * Drop every cached response. Called when the signed-in account changes
 * (`signIn`/`signOut` in `lib/auth.tsx`): the cache holds per-account data
 * (`/me/settings`, `/notifications`, the user-filtered `/history`), and
 * stale-while-revalidate must never serve one account's rows to another.
 */
export function clearCache(): void {
  generation += 1
  cache.clear()
  inflight.clear()
}

function setCache<T>(key: string, value: T): void {
  cache.set(key, value)
  const set = listeners.get(key)
  if (set) for (const fn of set) fn()
}

function subscribe(key: string, fn: () => void): () => void {
  let set = listeners.get(key)
  if (!set) {
    set = new Set()
    listeners.set(key, set)
  }
  set.add(fn)
  return () => {
    set.delete(fn)
    if (set.size === 0) listeners.delete(key)
  }
}

/**
 * Fetch on mount, optionally re-fetch on an interval.
 * Errors are kept and shown; they are never swallowed into an empty state,
 * because "no data" and "the API is down" must not look the same.
 */
export function useApi<T>(
  key: string,
  fetcher: (s?: AbortSignal) => Promise<T>,
  pollMs?: number,
): Async<T> {
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
      const gen = generation
      try {
        const next = await runDedupe(key, () => fetcherRef.current(undefined))
        // A clearCache() happened while the request was in flight: the response
        // belongs to the previous account, so it must not repaint this hook or
        // the shared cache. The next poll/mount fetches fresh under the new
        // generation.
        if (gen !== generation) return
        setCache(key, next)
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

    // A backgrounded tab used to keep polling all night — burning API calls and
    // Google Sheets quota for a page nobody is looking at. Skip the tick while
    // hidden, then refresh once on the way back so the first thing the user
    // sees is current rather than however stale the tab got.
    const onVisible = () => {
      if (document.visibilityState === 'visible') void run(false)
    }
    if (pollMs) {
      timer = window.setInterval(() => {
        if (document.visibilityState === 'visible') void run(false)
      }, pollMs)
      document.addEventListener('visibilitychange', onVisible)
    }

    return () => {
      controller.abort()
      if (timer) window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [key, pollMs, nonce])

  // Repaint when another hook refreshes this key. setData with the same object
  // reference is a no-op, so a poll writing identical data cannot loop.
  useEffect(() => {
    return subscribe(key, () => {
      const fresh = cache.get(key)
      if (fresh !== undefined) setData(fresh as T)
    })
  }, [key])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { data, error, loading, reload }
}
