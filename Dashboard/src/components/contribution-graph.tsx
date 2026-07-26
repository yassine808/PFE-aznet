import { useMemo } from 'react'
import { useI18n } from '@/lib/i18n'
import { toISODate } from '@/lib/metrics'
import type { ReportRow } from '@/lib/api'

const WEEKS = 53
const DAY_MS = 86_400_000

/**
 * Year heatmap of reporting activity, one cell per day.
 *
 * Sequential encoding: a single hue, light to dark, because the value is a
 * magnitude (reports that day). Never a rainbow, and never a diverging pair —
 * there is no meaningful midpoint in "how many reports arrived".
 */
export function ContributionGraph({ rows }: { rows: ReportRow[] }) {
  const { t, locale, dir } = useI18n()

  const { cells, max, total, activeDays } = useMemo(() => {
    const counts = new Map<string, number>()
    for (const r of rows) {
      const iso = toISODate(r.date)
      if (iso) counts.set(iso, (counts.get(iso) ?? 0) + 1)
    }

    // End on the last Saturday-or-today so the final column is the current week.
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const end = new Date(today.getTime() + (6 - today.getDay()) * DAY_MS)
    const start = new Date(end.getTime() - (WEEKS * 7 - 1) * DAY_MS)

    const out: { iso: string; count: number; future: boolean }[] = []
    for (let i = 0; i < WEEKS * 7; i++) {
      const d = new Date(start.getTime() + i * DAY_MS)
      const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      out.push({ iso, count: counts.get(iso) ?? 0, future: d > today })
    }

    return {
      cells: out,
      max: Math.max(...counts.values(), 1),
      total: [...counts.values()].reduce((a, b) => a + b, 0),
      activeDays: counts.size,
    }
  }, [rows])

  // Four steps plus an empty state. More steps than that stop being tellable apart.
  const level = (count: number) => {
    if (count === 0) return 0
    const ratio = count / max
    if (ratio <= 0.25) return 1
    if (ratio <= 0.5) return 2
    if (ratio <= 0.75) return 3
    return 4
  }

  const STEP = [
    'bg-line/60',
    'bg-accent/25',
    'bg-accent/50',
    'bg-accent/75',
    'bg-accent',
  ]

  const fmtDate = new Intl.DateTimeFormat(locale === 'ar' ? 'ar-MA' : locale === 'en' ? 'en-GB' : 'fr-FR', {
    dateStyle: 'medium',
  })

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto pb-1">
        <div
          className="grid grid-flow-col gap-[3px]"
          style={{ gridTemplateRows: 'repeat(7, 1fr)', direction: dir }}
          role="img"
          aria-label={t('graph.year')}
        >
          {cells.map((c) =>
            c.future ? (
              <span key={c.iso} className="size-[11px]" />
            ) : (
              <span
                key={c.iso}
                className={`size-[11px] rounded-[2px] ${STEP[level(c.count)]}`}
                title={`${fmtDate.format(new Date(c.iso))} · ${c.count}`}
              />
            ),
          )}
        </div>
      </div>

      <div className="text-ink-faint flex flex-wrap items-center justify-between gap-3 text-xs">
        <span>
          <span className="tabular">{total}</span> {t('graph.reportsIn')} <span className="tabular">{activeDays}</span>{' '}
          {t('graph.activeDays')}
        </span>
        <span className="flex items-center gap-1.5">
          {t('graph.less')}
          {STEP.map((s, i) => (
            <span key={i} className={`size-[11px] rounded-[2px] ${s}`} />
          ))}
          {t('graph.more')}
        </span>
      </div>
    </div>
  )
}
