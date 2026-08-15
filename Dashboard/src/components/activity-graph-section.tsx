import { useMemo } from 'react'
import { useI18n } from '@/lib/i18n'
import { ContributionGraph, type GraphRow } from '@/components/contribution-graph'

/**
 * Same graph, same slot, on every panel that browses reports by day (Daily,
 * Reports, Inbox) — switching between them keeps the year heatmap fixed in
 * place instead of re-laying-out per page.
 */
export function ActivityGraphSection({
  rows,
  date,
  onSelectDay,
}: {
  readonly rows: GraphRow[]
  /** ISO day to outline; also picks which year the heatmap opens on. */
  readonly date: string
  readonly onSelectDay: (iso: string) => void
}) {
  const { t } = useI18n()

  const year = Number(date.slice(0, 4)) || new Date().getFullYear()
  const years = useMemo(() => {
    const y = new Date().getFullYear()
    return [y, y - 1, y - 2]
  }, [])

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
        {t('graph.year')}
      </h2>

      <div className="flex items-start gap-5">
        <div className="min-w-0 flex-1">
          <ContributionGraph rows={rows} year={year} onSelectDay={onSelectDay} selectedDay={date} />
        </div>

        <fieldset className="m-0 flex shrink-0 flex-col gap-1 border-0 p-0">
          <legend className="sr-only">{t('weekly.year')}</legend>
          {years.map((y) => (
            <button
              key={y}
              type="button"
              onClick={() => onSelectDay(`${y}-01-01`)}
              aria-pressed={y === year}
              className={`tabular rounded px-2.5 py-1 text-xs transition-colors ${
                y === year
                  ? 'bg-slate-100 text-ink dark:bg-slate-850'
                  : 'text-ink-faint hover:text-ink'
              }`}
            >
              {y}
            </button>
          ))}
        </fieldset>
      </div>
    </section>
  )
}
