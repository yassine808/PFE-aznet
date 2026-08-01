import type { ReportRow } from '@/lib/api'

/**
 * Sheets hands back strings. Everything here parses defensively and returns 0
 * rather than NaN, so a malformed cell degrades one number instead of the page.
 */
export function num(v?: string): number {
  if (!v) return 0
  const parsed = Number.parseFloat(String(v).replace(',', '.'))
  return Number.isFinite(parsed) ? parsed : 0
}

export function isFlagged(v?: string): boolean {
  return ['true', 'vrai', 'oui', 'yes', '1'].includes((v ?? '').trim().toLowerCase())
}

/** Accepts both the ISO form n8n writes and the DD/MM/YYYY a human might type. */
export function toISODate(v?: string): string | null {
  if (!v) return null
  const raw = v.trim()
  const iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(raw)
  if (iso) return `${iso[1]}-${iso[2]}-${iso[3]}`
  const dmy = /^(\d{1,2})[/.](\d{1,2})[/.](\d{4})/.exec(raw)
  if (dmy) return `${dmy[3]}-${dmy[2].padStart(2, '0')}-${dmy[1].padStart(2, '0')}`
  return null
}

export function todayISO(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Local-date key for N days ago. Local, not UTC: `toISOString()` would shift the
 *  day by one in Africa/Casablanca and misalign against the API's local dates. */
export function daysAgoISO(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() - n)
  const pad = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export interface Totals {
  goulottes_m: number
  cables_m: number
  bureaux: number
  panneaux: number
}

/** "20:15" -> 1215 minutes past midnight. Returns null when the cell is unusable. */
export function minutesOf(heure?: string): number | null {
  const m = /^(\d{1,2})[:h.](\d{2})/.exec((heure ?? '').trim())
  if (!m) return null
  const h = Number(m[1])
  const min = Number(m[2])
  if (h > 23 || min > 59) return null
  return h * 60 + min
}

/** Renders a Sheet "HH:MM" cell in the chosen clock. 24h keeps a zero-padded
 *  "HH:MM"; 12h adds an explicit marker whatever the locale's default is.
 *  Returns the raw string untouched when the cell is unusable. */
export function clock(
  v: string | undefined,
  format: '24h' | '12h',
  am: string,
  pm: string,
): string {
  const at = minutesOf(v)
  if (at === null) return v ?? ''
  const h = Math.floor(at / 60)
  const m = at % 60
  const mm = String(m).padStart(2, '0')
  if (format === '24h') return `${String(h).padStart(2, '0')}:${mm}`
  const h12 = h % 12 || 12
  return `${h12}:${mm} ${h < 12 ? am : pm}`
}

export interface Metrics {
  today: number
  week: number
  total: number
  /** Rows whose date cell could not be parsed. Reported, never silently dropped. */
  undated: number
  flagged: number
  techniciens: number
  voiceShare: number | null
  totalsToday: Totals
  byChantier: { name: string; count: number; goulottes: number }[]
  byTechnicien: { name: string; count: number }[]
  recent: ReportRow[]
  /** Rows for the most recent day that actually has data, plus that day's ISO date. */
  dayRows: ReportRow[]
  dayISO: string | null
  /** True when the ribbon is showing an older day because nothing arrived today. */
  dayIsStale: boolean
  ledger: ReportRow[]
}

function totals(rows: ReportRow[]): Totals {
  return rows.reduce<Totals>(
    (acc, r) => ({
      goulottes_m: acc.goulottes_m + num(r.goulottes_m),
      cables_m: acc.cables_m + num(r.cables_m),
      bureaux: acc.bureaux + num(r.bureaux_termines),
      panneaux: acc.panneaux + num(r.panneaux_raccordes),
    }),
    { goulottes_m: 0, cables_m: 0, bureaux: 0, panneaux: 0 },
  )
}

function tally(rows: ReportRow[], key: (r: ReportRow) => string | undefined) {
  const map = new Map<string, { count: number; goulottes: number }>()
  for (const r of rows) {
    const name = (key(r) ?? '').trim()
    if (!name) continue
    const prev = map.get(name) ?? { count: 0, goulottes: 0 }
    map.set(name, { count: prev.count + 1, goulottes: prev.goulottes + num(r.goulottes_m) })
  }
  return [...map.entries()].map(([name, v]) => ({ name, ...v })).sort((a, b) => b.count - a.count)
}

export function computeMetrics(rows: ReportRow[]): Metrics {
  const today = todayISO()
  const weekStart = daysAgoISO(6)

  const dated = rows.map((r) => ({ row: r, iso: toISODate(r.date) }))
  const todayRows = dated.filter((d) => d.iso === today).map((d) => d.row)
  const weekRows = dated.filter((d) => d.iso !== null && d.iso >= weekStart).map((d) => d.row)

  const withChannel = rows.filter((r) => (r.canal ?? '').trim())
  const voice = withChannel.filter((r) => (r.lien_audio ?? '').trim()).length

  // The ribbon shows today when today has data, otherwise the newest day that does.
  // Showing an empty axis when reports exist would read as "the pipeline is dead".
  const knownDays = [
    ...new Set(dated.map((d) => d.iso).filter((d): d is string => d !== null)),
  ].sort((a, b) => a.localeCompare(b))
  const dayISO = todayRows.length ? today : (knownDays.at(-1) ?? null)
  const dayRows = dayISO ? dated.filter((d) => d.iso === dayISO).map((d) => d.row) : []

  return {
    today: todayRows.length,
    week: weekRows.length,
    total: rows.length,
    undated: dated.filter((d) => d.iso === null).length,
    flagged: rows.filter((r) => isFlagged(r.flag_review)).length,
    techniciens: new Set(rows.map((r) => (r.technicien ?? '').trim()).filter(Boolean)).size,
    voiceShare: rows.length ? Math.round((voice / rows.length) * 100) : null,
    // Totals follow the day the ribbon shows, so the numbers and the shape agree.
    totalsToday: totals(dayRows),
    byChantier: tally(rows, (r) => r.chantier).slice(0, 6),
    byTechnicien: tally(rows, (r) => r.technicien).slice(0, 6),
    // The Sheet appends, so the tail is the newest.
    recent: [...rows].reverse().slice(0, 6),
    dayRows,
    dayISO,
    dayIsStale: dayISO !== null && dayISO !== today,
    ledger: [...rows].reverse(),
  }
}

export function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d) return `${d}j ${h}h`
  if (h) return `${h}h ${m}m`
  return `${m}m`
}
