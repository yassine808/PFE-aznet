import type { ReportRow } from '@/lib/api'
import { isFlagged, num } from '@/lib/metrics'

/**
 * The aggregates the Daily and Weekly pages both draw. One module because they
 * are the same arithmetic over the same rows — when they were two copies, a
 * fix to one silently left the other showing different numbers for the same
 * work.
 */

/** The four quantities the pages have always led with, in their original
 *  order, each mapped to the locale key that names it. Kept first so existing
 *  data does not visually reshuffle; everything else is discovered. */
export const PRIMARY_QUANTITIES: Record<string, string> = {
  goulottes_m: 'metric.goulottes',
  cables_m: 'metric.cables',
  bureaux_termines: 'metric.bureaux',
  panneaux_raccordes: 'metric.panneaux',
}

/** Columns of the Rapports tab that carry meta, prose or identifiers. Some of
 *  them (`_row`, `confidence`) parse as numbers, so the numeric test alone is
 *  not enough to keep them out of a production tile. */
const NON_QUANTITY = new Set([
  '_row',
  'date',
  'heure',
  'canal',
  'technicien',
  'role',
  'chantier',
  'client',
  'type_activite',
  'autres_travaux',
  'observations',
  'remarques',
  'motif_arret',
  'motif_flag',
  'besoins',
  'prochaines_etapes',
  'resume',
  'Message',
  'confidence',
  'flag_review',
  'lien_audio',
  'correlation_id',
  'STT_model',
  'etages',
  'ailes',
  'locaux_techniques',
])

/** A cell that is a bare number and nothing else. `5 m de câble` is prose. */
const NUMERIC_CELL = /^-?\d+([.,]\d+)?$/

/**
 * Which quantity columns these rows actually carry.
 *
 * ponytail: the ceiling is the data — a column nobody has reported yet cannot
 * appear, so a brand-new bordereau article stays invisible until its first
 * message. The backend already owns the real catalogue
 * (`journal.quantity_columns()`, 35 fields); the upgrade path is an endpoint
 * serving it and reading that here instead of sniffing keys.
 */
export function quantityColumns(rows: readonly ReportRow[]): string[] {
  const extra = new Set<string>()
  for (const row of rows) {
    for (const [key, value] of Object.entries(row as unknown as Record<string, unknown>)) {
      if (key in PRIMARY_QUANTITIES || extra.has(key) || NON_QUANTITY.has(key)) continue
      const cell = typeof value === 'string' ? value.trim() : ''
      if (cell && NUMERIC_CELL.test(cell)) extra.add(key)
    }
  }
  // localeCompare, not the default sort: `Array.sort()` orders by UTF-16 code
  // unit, so a column whose label starts with an accent sorts after every
  // unaccented one. The vocabulary here is French.
  return [...Object.keys(PRIMARY_QUANTITIES), ...[...extra].sort((a, b) => a.localeCompare(b))]
}

/** `m` for metres, `min` for minutes, nothing otherwise — the unit lives in the
 *  schema field's own suffix, which is why no table is needed. */
export function unitOf(column: string): string {
  if (column.endsWith('_min')) return 'min'
  if (column.endsWith('_m')) return 'm'
  return ''
}

export interface QuantityTotal {
  readonly column: string
  readonly unit: string
  readonly value: number
}

export interface TechStat {
  readonly count: number
  readonly goulottes: number
  readonly flagged: number
}

export interface ReportStats {
  readonly totals: QuantityTotal[]
  readonly byTech: [string, TechStat][]
  readonly flagged: number
  readonly techniciens: number
  readonly chantiers: number
}

export function computeReportStats(rows: readonly ReportRow[]): ReportStats {
  const cells = rows as unknown as readonly Record<string, string | undefined>[]
  const totals = quantityColumns(rows)
    .map((column) => ({
      column,
      unit: unitOf(column),
      value: cells.reduce((sum, r) => sum + num(r[column]), 0),
    }))
    // A discovered column is only there because some row reported it, and a
    // row reporting `0` is enough — so a tile reading "Fibre 0 m" would say
    // nothing happened rather than nothing was tracked. The four originals
    // stay whatever their total, because a zero on them IS the day's news.
    .filter((q) => q.value !== 0 || q.column in PRIMARY_QUANTITIES)

  const byTech = new Map<string, TechStat>()
  for (const r of rows) {
    const k = (r.technicien ?? '').trim() || '—'
    const p = byTech.get(k) ?? { count: 0, goulottes: 0, flagged: 0 }
    byTech.set(k, {
      count: p.count + 1,
      goulottes: p.goulottes + num(r.goulottes_m),
      flagged: p.flagged + (isFlagged(r.flag_review) ? 1 : 0),
    })
  }

  return {
    totals,
    byTech: [...byTech.entries()].sort((a, b) => b[1].count - a[1].count),
    flagged: rows.filter((r) => isFlagged(r.flag_review)).length,
    techniciens: new Set(rows.map((r) => (r.technicien ?? '').trim()).filter(Boolean)).size,
    chantiers: new Set(rows.map((r) => (r.chantier ?? '').trim()).filter(Boolean)).size,
  }
}
