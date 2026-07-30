import type { ServiceSample } from '@/lib/api'
import type { ServiceState } from '@/lib/services'

export const SLOT_MS = 60_000
export const SLOTS = 60

const STATES: ServiceState[] = ['ok', 'warn', 'fail', 'idle']

function asState(raw: string): ServiceState | null {
  return (STATES as string[]).includes(raw) ? (raw as ServiceState) : null
}

/**
 * Projects Postgres samples onto a fixed timeline of the last SLOTS minutes so
 * every strip aligns column-for-column.
 *
 * A minute with no sample stays `null` and renders as an empty track. Filling
 * it forward would invent uptime nobody observed, which is the one thing an
 * availability chart must never do.
 */
export function timeline(samples: ServiceSample[], service: string): (ServiceState | null)[] {
  const now = Math.floor(Date.now() / SLOT_MS) * SLOT_MS
  const byBucket = new Map<number, ServiceState>()

  for (const s of samples) {
    if (s.service !== service) continue
    const t = Date.parse(s.ts)
    if (!Number.isFinite(t)) continue
    const state = asState(s.state)
    if (!state) continue
    // Last reading inside a minute wins; samples arrive oldest-first.
    byBucket.set(Math.floor(t / SLOT_MS) * SLOT_MS, state)
  }

  return Array.from(
    { length: SLOTS },
    (_, i) => byBucket.get(now - (SLOTS - 1 - i) * SLOT_MS) ?? null,
  )
}

/** Share of recorded slots that were healthy. Null when nothing was recorded. */
export function availability(slots: (ServiceState | null)[]): number | null {
  const seen = slots.filter((s): s is ServiceState => s !== null)
  if (seen.length === 0) return null
  return Math.round((seen.filter((s) => s === 'ok').length / seen.length) * 100)
}
