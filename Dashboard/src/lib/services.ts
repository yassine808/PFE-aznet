import type { Health, LogEntry, LogStats, N8nWorkflow } from '@/lib/api'

const INTL_LOCALE: Record<string, string> = { ar: 'ar-MA', en: 'en-GB', fr: 'fr-FR' }
function intlTag(locale: string): string {
  return INTL_LOCALE[locale] ?? 'fr-FR'
}

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
  const rtf = new Intl.RelativeTimeFormat(intlTag(locale), { numeric: 'auto' })
  const min = Math.round(age / 60_000)
  if (min < 60) return rtf.format(-min, 'minute')
  const h = Math.round(min / 60)
  if (h < 24) return rtf.format(-h, 'hour')
  return rtf.format(-Math.round(h / 24), 'day')
}

function lastOfChannel(logs: LogEntry[], channel: string): LogEntry | undefined {
  return logs.find((l) => l.channel === channel)
}

function apiRow(health: Health | null, healthError: string | null): ServiceRow {
  let state: ServiceState = 'idle'
  let captionKey = 'state.loading'
  if (healthError) {
    state = 'fail'
    captionKey = 'svc.unreachable'
  } else if (health) {
    state = 'ok'
    captionKey = 'svc.up'
  }
  return {
    key: 'api',
    labelKey: 'svc.api',
    state,
    captionKey,
    detail: health ? `v${health.version}` : undefined,
  }
}

function n8nRow(
  n8nReachable: boolean,
  workflow: N8nWorkflow | undefined,
  lastExecution: { status: string; startedAt: string } | null,
  locale: string,
): ServiceRow {
  const wfActive = workflow?.active ?? false
  let state: ServiceState = 'warn'
  let captionKey = 'svc.disarmed'
  if (!n8nReachable) {
    state = 'fail'
    captionKey = 'svc.unreachable'
  } else if (wfActive) {
    state = 'ok'
    captionKey = 'svc.armed'
  }
  return {
    key: 'n8n',
    labelKey: 'svc.n8n',
    state,
    captionKey,
    detail: lastExecution ? formatAge(lastExecution.startedAt, locale) : undefined,
  }
}

function channelRow(
  key: string,
  labelKey: string,
  channel: string,
  logs: LogEntry[],
  locale: string,
): ServiceRow {
  const last = lastOfChannel(logs, channel)
  const age = ageMs(last?.ts)
  let state: ServiceState = 'ok'
  let captionKey = 'svc.lastMessage'
  if (!last) {
    state = 'idle'
    captionKey = 'svc.noTraffic'
  } else if (last.level === 'error') {
    state = 'fail'
    captionKey = 'svc.lastFailed'
  } else if (age !== null && age > 48 * HOUR) {
    state = 'warn'
  }
  return { key, labelKey, state, captionKey, detail: last ? formatAge(last.ts, locale) : undefined }
}

function aiRow(logs: LogEntry[], health: Health | null): ServiceRow {
  const aiLogs = logs.filter((l) => l.stage === 'transcribed' || l.stage === 'extracted')
  const aiErrors = aiLogs.filter((l) => l.level === 'error').length
  const durations = aiLogs
    .map((l) => l.duration_ms)
    .filter((d): d is number => typeof d === 'number' && d > 0)
  const median =
    durations.length > 0
      ? [...durations].sort((a, b) => a - b)[Math.floor(durations.length / 2)]
      : null

  let state: ServiceState = 'ok'
  let captionKey = 'svc.up'
  if (aiLogs.length === 0) {
    state = 'idle'
    captionKey = 'svc.noTraffic'
  } else if (aiErrors > 0) {
    state = 'warn'
    captionKey = 'svc.someErrors'
  }

  return {
    key: 'ai',
    labelKey: 'svc.ai',
    state,
    captionKey,
    detail: [
      health?.stt_default,
      median !== null ? `${(median / 1000).toFixed(1)}s` : null,
      aiErrors ? `${aiErrors} err` : null,
    ]
      .filter(Boolean)
      .join(' · '),
  }
}

function sheetsRow(logs: LogEntry[], stats: LogStats | null, reportsOk: boolean): ServiceRow {
  const sheetLogs = logs.filter((l) => l.stage === 'sheet_written')
  const sheetErrors = sheetLogs.filter((l) => l.level === 'error').length
  const pending = stats?.pending_sheet_writes ?? 0

  let state: ServiceState = 'ok'
  let captionKey = 'svc.up'
  if (!reportsOk) {
    state = 'fail'
    captionKey = 'svc.unreachable'
  } else if (pending > 0) {
    state = 'warn'
    captionKey = 'svc.queued'
  } else if (sheetErrors > 0) {
    state = 'warn'
    captionKey = 'svc.someErrors'
  }

  return {
    key: 'sheets',
    labelKey: 'svc.sheets',
    state,
    captionKey,
    detail: pending > 0 ? `${pending}` : undefined,
  }
}

function postgresRow(logs: LogEntry[], stats: LogStats | null, logsError: string | null): ServiceRow {
  let state: ServiceState = 'idle'
  let captionKey = 'state.loading'
  if (logsError) {
    state = 'fail'
    captionKey = 'svc.unreachable'
  } else if (stats) {
    state = 'ok'
    captionKey = 'svc.up'
  }
  return {
    key: 'postgres',
    labelKey: 'svc.postgres',
    state,
    captionKey,
    detail: stats ? `${logs.length} · ${stats.retention_days}j` : undefined,
  }
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

  // /logs answering at all proves the API reached Postgres: the API prints
  // "[logs] DISABLED" and returns an error when DATABASE_URL is unset.
  return [
    apiRow(health, healthError),
    n8nRow(n8nReachable, workflow, lastExecution, locale),
    channelRow('telegram', 'svc.telegram', 'telegram', logs, locale),
    channelRow('whatsapp', 'svc.whatsapp', 'whatsapp', logs, locale),
    aiRow(logs, health),
    sheetsRow(logs, stats, reportsOk),
    postgresRow(logs, stats, logsError),
  ]
}
