import type { LogEntry } from '@/lib/api'

/**
 * The happy path a message walks, in order. Used for the funnel and for the
 * stage dots on each trace, so a missing stage is visible as a gap rather than
 * silently absent.
 */
export const STAGES = ['received', 'transcribed', 'extracted', 'sheet_written', 'replied'] as const
export type Stage = (typeof STAGES)[number]

export interface Trace {
  correlationId: string
  channel: string | null
  technicien: string | null
  /** Every event for this message, oldest first. */
  events: LogEntry[]
  /** Stage -> worst level seen for it. Absent means the stage never happened. */
  reached: Map<string, string>
  startedAt: number | null
  endedAt: number | null
  /** Wall-clock span of the whole message, ms. Null when timestamps are unusable. */
  totalMs: number | null
  hasError: boolean
}

function ts(e: LogEntry): number {
  const t = Date.parse(e.ts)
  return Number.isFinite(t) ? t : NaN
}

/**
 * Groups flat log rows into one trace per message.
 *
 * The correlation_id is minted by n8n at reception and carried by the API too,
 * so this is the only place the two processes' stories are joined back into a
 * single timeline. Rows without one are dropped: they cannot be attributed to
 * a message, and inventing a bucket for them would fabricate traces.
 */
export function buildTraces(logs: LogEntry[]): Trace[] {
  const byId = new Map<string, LogEntry[]>()
  for (const l of logs) {
    const id = (l.correlation_id ?? '').trim()
    if (!id) continue
    const list = byId.get(id)
    if (list) list.push(l)
    else byId.set(id, [l])
  }

  const traces: Trace[] = []
  for (const [correlationId, raw] of byId) {
    const events = [...raw].sort((a, b) => (ts(a) || 0) - (ts(b) || 0))

    const reached = new Map<string, string>()
    for (const e of events) {
      // Worst level wins: one error at a stage marks that stage failed even if
      // a later info row for the same stage arrives.
      const prev = reached.get(e.stage)
      reached.set(e.stage, prev === 'error' || e.level === 'error' ? 'error' : prev === 'warn' ? 'warn' : e.level)
    }

    const times = events.map(ts).filter((t) => Number.isFinite(t))
    const startedAt = times.length ? Math.min(...times) : null
    const endedAt = times.length ? Math.max(...times) : null

    traces.push({
      correlationId,
      channel: events.find((e) => e.channel)?.channel ?? null,
      technicien: events.find((e) => e.technicien)?.technicien ?? null,
      events,
      reached,
      startedAt,
      endedAt,
      totalMs: startedAt !== null && endedAt !== null ? endedAt - startedAt : null,
      hasError: events.some((e) => e.level === 'error'),
    })
  }

  // Newest first: an operator opens this panel to see what just broke.
  return traces.sort((a, b) => (b.startedAt ?? 0) - (a.startedAt ?? 0))
}

export interface FunnelStep {
  stage: Stage
  /** Messages that reached this stage at all. */
  count: number
  /** Messages that reached it with an error. */
  errors: number
  /** Messages lost between the previous stage and this one. */
  dropped: number
}

/** Distinct messages reaching each stage, with the loss between steps. */
export function buildFunnel(traces: Trace[]): FunnelStep[] {
  let previous: number | null = null
  return STAGES.map((stage) => {
    const at = traces.filter((t) => t.reached.has(stage))
    const count = at.length
    const step: FunnelStep = {
      stage,
      count,
      errors: at.filter((t) => t.reached.get(stage) === 'error').length,
      dropped: previous === null ? 0 : Math.max(previous - count, 0),
    }
    previous = count
    return step
  })
}

/** Median and p95 of `duration_ms` for one stage. Null when nothing is timed. */
export function latency(logs: LogEntry[], stage: string): { median: number; p95: number; n: number } | null {
  const values = logs
    .filter((l) => l.stage === stage && typeof l.duration_ms === 'number' && l.duration_ms! > 0)
    .map((l) => l.duration_ms as number)
    .sort((a, b) => a - b)
  if (values.length === 0) return null
  const pick = (q: number) => values[Math.min(values.length - 1, Math.floor(values.length * q))]
  return { median: pick(0.5), p95: pick(0.95), n: values.length }
}
