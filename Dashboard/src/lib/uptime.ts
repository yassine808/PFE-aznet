import { useEffect, useRef, useState } from 'react'
import type { ServiceRow, ServiceState } from '@/lib/services'

export const SLOT_MS = 60_000
export const SLOTS = 60

export interface Sample {
  /** Minute bucket, epoch ms floored to SLOT_MS. */
  t: number
  states: Record<string, ServiceState>
}

const STORAGE_KEY = 'aznet.uptime'

function load(): Sample[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as Sample[]
    return Array.isArray(parsed) ? parsed.slice(-SLOTS) : []
  } catch {
    return []
  }
}

function save(samples: Sample[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(samples.slice(-SLOTS)))
  } catch {
    // Storage full or blocked: history is a convenience, never a hard dependency.
  }
}

/**
 * Records one sample per minute per service and keeps the last hour.
 *
 * IMPORTANT and deliberately visible in the UI: this is a *dashboard-side*
 * record. It only observes while the page is open, so gaps mean "nobody was
 * watching", not "the service was down". A true uptime monitor would have to
 * sample server-side; presenting this as one would be a lie about coverage.
 */
export function useUptimeHistory(rows: ServiceRow[]): Sample[] {
  const [samples, setSamples] = useState<Sample[]>(load)
  const rowsRef = useRef(rows)
  rowsRef.current = rows

  useEffect(() => {
    const record = () => {
      const current = rowsRef.current
      if (current.length === 0) return
      const bucket = Math.floor(Date.now() / SLOT_MS) * SLOT_MS
      const states: Record<string, ServiceState> = {}
      for (const r of current) states[r.key] = r.state

      setSamples((prev) => {
        const last = prev.at(-1)
        // One entry per minute bucket; a later reading in the same minute wins.
        const next = last?.t === bucket ? [...prev.slice(0, -1), { t: bucket, states }] : [...prev, { t: bucket, states }]
        const trimmed = next.slice(-SLOTS)
        save(trimmed)
        return trimmed
      })
    }

    record()
    const timer = window.setInterval(record, SLOT_MS)
    return () => window.clearInterval(timer)
  }, [])

  return samples
}

/**
 * Projects samples onto a fixed timeline of the last SLOTS minutes so every
 * strip aligns column-for-column, with `null` where no sample exists.
 */
export function timeline(samples: Sample[], key: string): (ServiceState | null)[] {
  const now = Math.floor(Date.now() / SLOT_MS) * SLOT_MS
  const byBucket = new Map(samples.map((s) => [s.t, s.states[key]]))
  return Array.from({ length: SLOTS }, (_, i) => {
    const bucket = now - (SLOTS - 1 - i) * SLOT_MS
    return byBucket.get(bucket) ?? null
  })
}

/** Share of recorded slots that were healthy. Null when nothing was recorded. */
export function availability(slots: (ServiceState | null)[]): number | null {
  const seen = slots.filter((s): s is ServiceState => s !== null)
  if (seen.length === 0) return null
  return Math.round((seen.filter((s) => s === 'ok').length / seen.length) * 100)
}
