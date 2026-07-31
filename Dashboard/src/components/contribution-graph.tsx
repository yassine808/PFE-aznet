import { useMemo } from 'react'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
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
  selectedDay,
  cellHeight,
}: {
  readonly rows: ReportRow[]
  /** Calendar year to render. Defaults to a rolling 53 weeks ending today. */
  readonly year?: number
  readonly onSelectDay?: (iso: string) => void
  readonly onSelectWeek?: (mondayIso: string) => void
  readonly selectedWeek?: string
  /** ISO day to outline as the current selection, e.g. the Daily panel's date. */
  readonly selectedDay?: string
  /**
   * Fixed row height in px. Default cells are square, so height is dictated by
   * however wide the panel is; set this when the graph is the main object on
   * the page and should read taller than 53 columns of width would allow.
   */
  readonly cellHeight?: number
}) {
  const { t, locale, dir } = useI18n()
  const intlLocale = intlLocaleOf(locale)

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

    const first =
      year !== undefined
        ? weekStart(new Date(year, 0, 1))
        : weekStart(new Date(today.getTime() - 52 * 7 * DAY_MS))
    const lastDay = year !== undefined ? new Date(year, 11, 31) : today
    const weekCount = Math.ceil((weekStart(lastDay).getTime() - first.getTime()) / (7 * DAY_MS)) + 1

    const cols: {
      monday: Date
      days: { date: Date; iso: string; count: number; inScope: boolean }[]
    }[] = []
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
    if (ratio <= 0.25) return 1
    if (ratio <= 0.5) return 2
    return ratio <= 0.75 ? 3 : 4
  }

  // Month label sits above the first column whose Monday starts a new month.
  const monthLabels = useMemo(() => {
    const fmtMonth = new Intl.DateTimeFormat(intlLocale, { month: 'short' })
    return weeks.map((w, i) => {
      const prev = weeks[i - 1]
      const label =
        !prev || prev.monday.getMonth() !== w.monday.getMonth() ? fmtMonth.format(w.monday) : ''
      return { key: isoOf(w.monday), label }
    })
  }, [weeks, intlLocale])

  // Monday, Wednesday, Friday only: labelling all seven crowds an 11px row.
  const dayLabels = useMemo(() => {
    const fmtDay = new Intl.DateTimeFormat(intlLocale, { weekday: 'short' })
    const monday = weekStart(new Date())
    return Array.from({ length: 7 }, (_, i) => {
      const date = new Date(monday.getTime() + i * DAY_MS)
      return { key: isoOf(date), label: i % 2 === 0 ? fmtDay.format(date) : '' }
    })
  }, [intlLocale])

  const fmtDate = new Intl.DateTimeFormat(intlLocale, { dateStyle: 'medium' })
  const interactive = Boolean(onSelectDay || onSelectWeek)
  const todayIso = isoOf(new Date())
  const rowTemplate = cellHeight ? `repeat(7, ${cellHeight}px)` : 'repeat(7, 1fr)'
  // Square cells only when height is width-driven; a fixed row height means the
  // cell must fill its track instead, otherwise it collapses back to a square.
  const cellShape = cellHeight ? 'h-full w-full' : 'aspect-square w-full'

  /*
   * Today and "the day you picked" are different questions, so they get
   * different marks: today is a hairline outline that is always present, the
   * selection is a thick accent outline. Outline, not ring — ring-offset would
   * need a solid offset colour, and these cells sit on a transparent panel.
   */
  const mark = (iso: string) => {
    if (iso === selectedDay) return ' outline outline-2 outline-accent'
    if (iso === todayIso) return ' outline outline-1 outline-ink-muted'
    return ''
  }

  type Day = { date: Date; iso: string; count: number; inScope: boolean }
  const renderDay = (d: Day) => {
    if (!d.inScope) return <span key={d.iso} className={cellShape} />
    if (!onSelectDay) {
      return (
        <span
          key={d.iso}
          className={`${cellShape} rounded-[2px] ${STEP[level(d.count)]}${mark(d.iso)}`}
          title={`${fmtDate.format(d.date)} · ${d.count}`}
        />
      )
    }
    return (
      <button
        key={d.iso}
        type="button"
        onClick={() => onSelectDay(d.iso)}
        className={`${cellShape} rounded-[2px] transition-transform hover:scale-125 ${STEP[level(d.count)]}${mark(d.iso)}`}
        title={`${fmtDate.format(d.date)} · ${d.count}`}
        aria-label={`${fmtDate.format(d.date)} · ${d.count}`}
      />
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {/*
        No horizontal scroll: columns are fractional and cells are square, so the
        whole year compresses to fit whatever width the panel has. Fixed-px cells
        would always overflow at 53 columns.
      */}
      <div className="pb-1">
        <div className="flex gap-1.5" style={{ direction: dir }}>
          {/* Weekday gutter */}
          <div
            className="grid shrink-0 gap-[2px] pt-[14px]"
            style={{ gridTemplateRows: rowTemplate }}
          >
            {dayLabels.map((d) => (
              <span
                key={d.key}
                className="text-ink-faint flex items-center text-[8px] leading-none capitalize"
              >
                {d.label}
              </span>
            ))}
          </div>

          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="grid auto-cols-fr grid-flow-col gap-[2px]">
              {monthLabels.map((m) => (
                <span
                  key={m.key}
                  className="text-ink-faint overflow-visible text-[8px] whitespace-nowrap capitalize"
                >
                  {m.label}
                </span>
              ))}
            </div>

            <div className="grid auto-cols-fr grid-flow-col gap-[2px]">
              {weeks.map((w) => {
                const isoMonday = isoOf(w.monday)
                const weekSelected = selectedWeek === isoMonday
                // onSelectWeek and onSelectDay are never both passed by any caller today
                // (see contribution-graph.tsx callers) — this component would need to drop
                // the week-level button below if a caller ever combined the two, since a
                // <button> cannot contain the per-day <button>s rendered further down.
                const WeekWrapper = onSelectWeek ? 'button' : 'div'
                return (
                  <WeekWrapper
                    key={isoMonday}
                    type={onSelectWeek ? 'button' : undefined}
                    className={`grid min-w-0 gap-[2px] rounded-[3px] text-left ${
                      onSelectWeek ? 'cursor-pointer' : ''
                    } ${weekSelected ? 'ring-accent ring-2 ring-offset-1 ring-offset-transparent' : ''}`}
                    style={{ gridTemplateRows: rowTemplate }}
                    onClick={onSelectWeek ? () => onSelectWeek(isoMonday) : undefined}
                    aria-label={onSelectWeek ? `${t('weekly.week')} ${isoMonday}` : undefined}
                  >
                    {w.days.map(renderDay)}
                  </WeekWrapper>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      <div className="text-ink-faint flex flex-wrap items-center justify-between gap-3 text-xs">
        <span>
          <span className="tabular">{total}</span> {t('graph.reportsIn')}{' '}
          <span className="tabular">{activeDays}</span> {t('graph.activeDays')}
          {interactive && onSelectDay ? ` · ${t('graph.clickHint')}` : ''}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="outline-ink-muted size-[11px] rounded-[2px] outline outline-1" />
          {t('graph.today')}
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
