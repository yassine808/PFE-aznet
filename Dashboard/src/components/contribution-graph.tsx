import { useMemo } from 'react'
import { useI18n } from '@/lib/i18n'
import { toISODate } from '@/lib/metrics'
import type { ReportRow } from '@/lib/api'

const DAY_MS = 86_400_000

export function isoOf(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Monday of the week containing `d`. ISO weeks start Monday. */
export function weekStart(d: Date) {
  const c = new Date(d)
  c.setHours(0, 0, 0, 0)
  return new Date(c.getTime() - ((c.getDay() + 6) % 7) * DAY_MS)
}

const STEP = ['bg-line/60', 'bg-accent/25', 'bg-accent/50', 'bg-accent/75', 'bg-accent']

/**
 * Year heatmap of reporting activity, one cell per day, Monday-first columns.
 *
 * Sequential encoding — a single hue stepped by lightness — because the value
 * is a magnitude. Five steps, not ten: beyond roughly five, alpha steps stop
 * being rankable by eye and the extra precision is unreadable.
 */
export function ContributionGraph({
  rows,
  year,
  onSelectDay,
  onSelectWeek,
  selectedWeek,
}: {
  rows: ReportRow[]
  /** Calendar year to render. Defaults to a rolling 53 weeks ending today. */
  year?: number
  onSelectDay?: (iso: string) => void
  onSelectWeek?: (mondayIso: string) => void
  selectedWeek?: string
}) {
  const { t, locale, dir } = useI18n()
  const intlLocale = locale === 'ar' ? 'ar-MA' : locale === 'en' ? 'en-GB' : 'fr-FR'

  const counts = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of rows) {
      const iso = toISODate(r.date)
      if (iso) map.set(iso, (map.get(iso) ?? 0) + 1)
    }
    return map
  }, [rows])

  const { weeks, max, total, activeDays } = useMemo(() => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)

    const first = year !== undefined ? weekStart(new Date(year, 0, 1)) : weekStart(new Date(today.getTime() - 52 * 7 * DAY_MS))
    const lastDay = year !== undefined ? new Date(year, 11, 31) : today
    const weekCount = Math.ceil((weekStart(lastDay).getTime() - first.getTime()) / (7 * DAY_MS)) + 1

    const cols: { monday: Date; days: { date: Date; iso: string; count: number; inScope: boolean }[] }[] = []
    let sum = 0
    let active = 0
    let peak = 1

    for (let w = 0; w < weekCount; w++) {
      const monday = new Date(first.getTime() + w * 7 * DAY_MS)
      const days = Array.from({ length: 7 }, (_, i) => {
        const date = new Date(monday.getTime() + i * DAY_MS)
        const iso = isoOf(date)
        const count = counts.get(iso) ?? 0
        const inScope = date <= today && (year === undefined || date.getFullYear() === year)
        if (inScope) {
          sum += count
          if (count > 0) active++
          if (count > peak) peak = count
        }
        return { date, iso, count, inScope }
      })
      cols.push({ monday, days })
    }

    return { weeks: cols, max: peak, total: sum, activeDays: active }
  }, [counts, year])

  const level = (count: number) => {
    if (count === 0) return 0
    const ratio = count / max
    return ratio <= 0.25 ? 1 : ratio <= 0.5 ? 2 : ratio <= 0.75 ? 3 : 4
  }

  // Month label sits above the first column whose Monday starts a new month.
  const monthLabels = useMemo(() => {
    const fmtMonth = new Intl.DateTimeFormat(intlLocale, { month: 'short' })
    return weeks.map((w, i) => {
      const prev = weeks[i - 1]
      return !prev || prev.monday.getMonth() !== w.monday.getMonth() ? fmtMonth.format(w.monday) : ''
    })
  }, [weeks, intlLocale])

  // Monday, Wednesday, Friday only: labelling all seven crowds an 11px row.
  const dayLabels = useMemo(() => {
    const fmtDay = new Intl.DateTimeFormat(intlLocale, { weekday: 'short' })
    const monday = weekStart(new Date())
    return Array.from({ length: 7 }, (_, i) =>
      i % 2 === 0 ? fmtDay.format(new Date(monday.getTime() + i * DAY_MS)) : '',
    )
  }, [intlLocale])

  const fmtDate = new Intl.DateTimeFormat(intlLocale, { dateStyle: 'medium' })
  const interactive = Boolean(onSelectDay || onSelectWeek)

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto pb-1">
        <div className="flex gap-1.5" style={{ direction: dir }}>
          {/* Weekday gutter */}
          <div className="grid shrink-0 gap-[3px] pt-[15px]" style={{ gridTemplateRows: 'repeat(7, 11px)' }}>
            {dayLabels.map((d, i) => (
              <span key={i} className="text-ink-faint h-[11px] text-[9px] leading-[11px] capitalize">
                {d}
              </span>
            ))}
          </div>

          <div className="flex flex-col gap-1">
            <div className="flex gap-[3px]">
              {monthLabels.map((label, i) => (
                <span key={i} className="text-ink-faint w-[11px] text-[9px] whitespace-nowrap capitalize">
                  {label}
                </span>
              ))}
            </div>

            <div className="flex gap-[3px]">
              {weeks.map((w) => {
                const isoMonday = isoOf(w.monday)
                const weekSelected = selectedWeek === isoMonday
                return (
                  <div
                    key={isoMonday}
                    className={`grid gap-[3px] rounded-[3px] ${
                      onSelectWeek ? 'cursor-pointer' : ''
                    } ${weekSelected ? 'ring-accent ring-2 ring-offset-1 ring-offset-transparent' : ''}`}
                    style={{ gridTemplateRows: 'repeat(7, 11px)' }}
                    onClick={onSelectWeek ? () => onSelectWeek(isoMonday) : undefined}
                    role={onSelectWeek ? 'button' : undefined}
                    tabIndex={onSelectWeek ? 0 : undefined}
                    onKeyDown={
                      onSelectWeek
                        ? (e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault()
                              onSelectWeek(isoMonday)
                            }
                          }
                        : undefined
                    }
                    aria-label={onSelectWeek ? `${t('weekly.week')} ${isoMonday}` : undefined}
                  >
                    {w.days.map((d) =>
                      !d.inScope ? (
                        <span key={d.iso} className="size-[11px]" />
                      ) : onSelectDay ? (
                        <button
                          key={d.iso}
                          type="button"
                          onClick={() => onSelectDay(d.iso)}
                          className={`size-[11px] rounded-[2px] transition-transform hover:scale-125 ${STEP[level(d.count)]}`}
                          title={`${fmtDate.format(d.date)} · ${d.count}`}
                          aria-label={`${fmtDate.format(d.date)} · ${d.count}`}
                        />
                      ) : (
                        <span
                          key={d.iso}
                          className={`size-[11px] rounded-[2px] ${STEP[level(d.count)]}`}
                          title={`${fmtDate.format(d.date)} · ${d.count}`}
                        />
                      ),
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      <div className="text-ink-faint flex flex-wrap items-center justify-between gap-3 text-xs">
        <span>
          <span className="tabular">{total}</span> {t('graph.reportsIn')} <span className="tabular">{activeDays}</span>{' '}
          {t('graph.activeDays')}
          {interactive && onSelectDay ? ` · ${t('graph.clickHint')}` : ''}
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
