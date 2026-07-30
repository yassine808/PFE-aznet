import type { Health, LogEntry, LogStats, N8nWorkflow } from '@/lib/api'

export type ServiceState = 'ok' | 'warn' | 'fail' | 'idle'

export interface ServiceRow {
  key: string
  /** Locale key for the service name. */
  labelKey: string
  state: ServiceState
  /** Locale key for the state caption. */
  captionKey: string
  /** Free-text detail already formatted (timestamp, count, duration). */
  detail?: string
}

const HOUR = 3_600_000

function ageMs(iso?: string | null): number | null {
  if (!iso) return null
  const t = Date.parse(iso)
  return Number.isFinite(t) ? Date.now() - t : null
}

export function formatAge(iso: string | null | undefined, locale: string): string {
  const age = ageMs(iso)
  if (age === null) return '—'
  const rtf = new Intl.RelativeTimeFormat(
    locale === 'ar' ? 'ar-MA' : locale === 'en' ? 'en-GB' : 'fr-FR',
    {
      numeric: 'auto',
    },
  )
  const min = Math.round(age / 60_000)
  if (min < 60) return rtf.format(-min, 'minute')
  const h = Math.round(min / 60)
  if (h < 24) return rtf.format(-h, 'hour')
  return rtf.format(-Math.round(h / 24), 'day')
}

function lastOfChannel(logs: LogEntry[], channel: string): LogEntry | undefined {
  return logs.find((l) => l.channel === channel)
}

/**
 * Derives one row per moving part of the pipeline.
 *
 * Every state is backed by an observation, never by an assumption:
 *   - a channel with no traffic is `idle`, not `fail` (silence is not breakage)
 *   - a channel whose last event is an error is `fail`
 *   - stale traffic on a channel that normally carries some is `warn`
 * Conflating "nothing arrived" with "it is broken" is the specific failure this
 * dashboard exists to prevent.
 */
export function buildServices(input: {
  health: Health | null
  healthError: string | null
  logs: LogEntry[]
  stats: LogStats | null
  logsError: string | null
  reportsOk: boolean
  n8nReachable: boolean
  workflow: N8nWorkflow | undefined
  lastExecution: { status: string; startedAt: string } | null
  locale: string
}): ServiceRow[] {
  const {
    health,
    healthError,
    logs,
    stats,
    logsError,
    reportsOk,
    n8nReachable,
    workflow,
    lastExecution,
    locale,
  } = input

  const rows: ServiceRow[] = []

  // ── API ────────────────────────────────────────────────────────────────
  rows.push({
    key: 'api',
    labelKey: 'svc.api',
    state: healthError ? 'fail' : health ? 'ok' : 'idle',
    captionKey: healthError ? 'svc.unreachable' : health ? 'svc.up' : 'state.loading',
    detail: health ? `v${health.version}` : undefined,
  })

  // ── n8n orchestrator ───────────────────────────────────────────────────
  const wfActive = workflow?.active ?? false
  rows.push({
    key: 'n8n',
    labelKey: 'svc.n8n',
    state: !n8nReachable ? 'fail' : wfActive ? 'ok' : 'warn',
    captionKey: !n8nReachable ? 'svc.unreachable' : wfActive ? 'svc.armed' : 'svc.disarmed',
    detail: lastExecution ? formatAge(lastExecution.startedAt, locale) : undefined,
  })

  // ── Reception channels ─────────────────────────────────────────────────
  for (const [key, labelKey, channel] of [
    ['telegram', 'svc.telegram', 'telegram'],
    ['whatsapp', 'svc.whatsapp', 'whatsapp'],
  ] as const) {
    const last = lastOfChannel(logs, channel)
    const age = ageMs(last?.ts)
    const state: ServiceState = !last
      ? 'idle'
      : last.level === 'error'
        ? 'fail'
        : age !== null && age > 48 * HOUR
          ? 'warn'
          : 'ok'
    rows.push({
      key,
      labelKey,
      state,
      captionKey: !last ? 'svc.noTraffic' : state === 'fail' ? 'svc.lastFailed' : 'svc.lastMessage',
      detail: last ? formatAge(last.ts, locale) : undefined,
    })
  }

  // ── AI: transcription + extraction ─────────────────────────────────────
  const aiLogs = logs.filter((l) => l.stage === 'transcribed' || l.stage === 'extracted')
  const aiErrors = aiLogs.filter((l) => l.level === 'error').length
  const durations = aiLogs
    .map((l) => l.duration_ms)
    .filter((d): d is number => typeof d === 'number' && d > 0)
  const median =
    durations.length > 0
      ? [...durations].sort((a, b) => a - b)[Math.floor(durations.length / 2)]
      : null
  rows.push({
    key: 'ai',
    labelKey: 'svc.ai',
    state: aiLogs.length === 0 ? 'idle' : aiErrors > 0 ? 'warn' : 'ok',
    captionKey: aiLogs.length === 0 ? 'svc.noTraffic' : aiErrors > 0 ? 'svc.someErrors' : 'svc.up',
    detail: [
      health?.stt_default,
      median !== null ? `${(median / 1000).toFixed(1)}s` : null,
      aiErrors ? `${aiErrors} err` : null,
    ]
      .filter(Boolean)
      .join(' · '),
  })

  // ── Google Sheets ──────────────────────────────────────────────────────
  const sheetLogs = logs.filter((l) => l.stage === 'sheet_written')
  const sheetErrors = sheetLogs.filter((l) => l.level === 'error').length
  const pending = stats?.pending_sheet_writes ?? 0
  rows.push({
    key: 'sheets',
    labelKey: 'svc.sheets',
    state: !reportsOk ? 'fail' : pending > 0 || sheetErrors > 0 ? 'warn' : 'ok',
    captionKey: !reportsOk
      ? 'svc.unreachable'
      : pending > 0
        ? 'svc.queued'
        : sheetErrors > 0
          ? 'svc.someErrors'
          : 'svc.up',
    detail: pending > 0 ? `${pending}` : undefined,
  })

  // ── PostgreSQL event store ─────────────────────────────────────────────
  // /logs answering at all proves the API reached Postgres: the API prints
  // "[logs] DISABLED" and returns an error when DATABASE_URL is unset.
  rows.push({
    key: 'postgres',
    labelKey: 'svc.postgres',
    state: logsError ? 'fail' : stats ? 'ok' : 'idle',
    captionKey: logsError ? 'svc.unreachable' : stats ? 'svc.up' : 'state.loading',
    detail: stats ? `${logs.length} · ${stats.retention_days}j` : undefined,
  })

  return rows
}
