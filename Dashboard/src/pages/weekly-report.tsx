import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { ArrowUUpLeftIcon, CalendarBlankIcon } from '@phosphor-icons/react'
import { api, generateDailyReport, useApi, type DailyReportContent } from '@/lib/api'
import { isFlagged, num, toISODate } from '@/lib/metrics'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { useHeaderAction } from '@/lib/page-header'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { ContributionGraph, isoOf as iso, weekStart } from '@/components/contribution-graph'
import { GenerateButton } from '@/components/generate-button'
import { NextRun } from '@/components/next-run'
import { PeriodPicker } from '@/components/period-picker'
import { ReportEditor } from '@/components/report-editor'
import { ReportImageCard } from '@/components/report-image'
import { cn } from '@/lib/utils'

const DAY_MS = 86_400_000

export function WeeklyReportPage({ initialWeek }: { readonly initialWeek?: string }) {
  const { t, locale } = useI18n()
  const reports = useApi('reports', api.reports)
  // Selected week as its Monday — `#/weekly?week=2026-08-03` from the report
  // mail, otherwise the current week. Initial value only, as on the Daily page.
  const [selected, setSelected] = useState(() => initialWeek || iso(weekStart(new Date())))
  const [year, setYear] = useState(() =>
    Number(initialWeek?.slice(0, 4)) || new Date().getFullYear(),
  )
  const [content, setContent] = useState<DailyReportContent | null>(null)
  const [busy, setBusy] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  // The illustrated card, held here so the editor can embed it in the .docx.
  const [image, setImage] = useState<string | null>(null)

  const fmt = useMemo(() => new Intl.NumberFormat(intlLocaleOf(locale)), [locale])
  const dayName = useMemo(
    () => new Intl.DateTimeFormat(intlLocaleOf(locale), { weekday: 'short' }),
    [locale],
  )

  const start = useMemo(() => {
    const [y, m, d] = selected.split('-').map(Number)
    return new Date(y, m - 1, d)
  }, [selected])
  const days = useMemo(
    () => Array.from({ length: 7 }, (_, i) => new Date(start.getTime() + i * DAY_MS)),
    [start],
  )
  /*
   * The week's one name — `2026-08-03 → 2026-08-09`, the same shape the
   * scheduler writes (`jobs.send_weekly_report`).
   *
   * It has to be a single variable because two calls on this page name the same
   * report: the generator stores it under this label in `manager_reports`, and
   * the editor stores its versions and its mirror under whatever `period` it is
   * handed. When those were two expressions they disagreed — the editor passed
   * the Monday alone, so saving an edit wrote a *second* row and, since that
   * table is keyed `(manager_id, period)`, silently overwrote that Monday's
   * daily report with the week's text.
   */
  const label = useMemo(() => `${iso(days[0])} → ${iso(days[6])}`, [days])

  // The same week the picker shows, written the way the reader's locale writes
  // it. `label` stays ISO because it is the report's stored key, not prose.
  const rangeLabel = useMemo(() => {
    const short = new Intl.DateTimeFormat(intlLocaleOf(locale), {
      day: 'numeric',
      month: 'long',
    })
    return `${short.format(days[0])} – ${short.format(days[6])}`
  }, [days, locale])

  // The most recent week that has rows, as its Monday — the empty state's way out.
  const lastWeekWithData = useMemo(() => {
    let best: string | null = null
    for (const r of reports.data?.reports ?? []) {
      const d = toISODate(r.date)
      if (d && (best === null || d > best)) best = d
    }
    if (!best) return null
    const [y, m, day] = best.split('-').map(Number)
    const mondayOf = iso(weekStart(new Date(y, m - 1, day)))
    return mondayOf === selected ? null : mondayOf
  }, [reports.data, selected])

  // Current year plus the two before it, newest first.
  const years = useMemo(() => {
    const y = new Date().getFullYear()
    return [y, y - 1, y - 2]
  }, [])

  const week = useMemo(() => {
    const rows = (reports.data?.reports ?? []).filter((r) => {
      const d = toISODate(r.date)
      return d !== null && d >= iso(days[0]) && d <= iso(days[6])
    })

    const perDay = days.map((d) => rows.filter((r) => toISODate(r.date) === iso(d)))
    const totals = rows.reduce(
      (a, r) => ({
        goulottes: a.goulottes + num(r.goulottes_m),
        cables: a.cables + num(r.cables_m),
        bureaux: a.bureaux + num(r.bureaux_termines),
        panneaux: a.panneaux + num(r.panneaux_raccordes),
      }),
      { goulottes: 0, cables: 0, bureaux: 0, panneaux: 0 },
    )

    const byTech = new Map<string, { count: number; goulottes: number; flagged: number }>()
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
      rows,
      perDay,
      totals,
      byTech: [...byTech.entries()].sort((a, b) => b[1].count - a[1].count),
      flagged: rows.filter((r) => isFlagged(r.flag_review)).length,
      techniciens: new Set(rows.map((r) => (r.technicien ?? '').trim()).filter(Boolean)).size,
      chantiers: new Set(rows.map((r) => (r.chantier ?? '').trim()).filter(Boolean)).size,
    }
  }, [reports.data, days])

  /*
   * There is no dedicated weekly endpoint, and adding one would mean a second
   * prompt to maintain. POST /daily-report already takes an arbitrary row set
   * and a label, so the week's rows go through it unchanged.
   */
  const generate = async () => {
    setBusy(true)
    setGenError(null)
    try {
      setContent(await generateDailyReport(label, week.rows))
    } catch (err) {
      setGenError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  // Beside the page title, same as the Daily page.
  useHeaderAction(
    <GenerateButton busy={busy} disabled={week.rows.length === 0} onClick={generate} />,
    [busy, week.rows.length, label, locale],
  )

  if (reports.error) return <ErrorState message={reports.error} onRetry={reports.reload} />
  if (reports.loading) return <Skeleton className="mt-8 h-64 rounded-xl" />

  const maxDay = Math.max(...week.perDay.map((d) => d.length), 1)

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-8 pt-8"
    >
      {/* The year graph takes the full width — it is how a week is chosen, so
          it gets the room rather than a right-hand column. */}
      <section className="flex flex-col gap-3">
        <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
          {t('weekly.pickWeek')}
        </h2>

        <div className="flex items-start gap-5">
          <div className="min-w-0 flex-1">
            <ContributionGraph
              rows={reports.data?.reports ?? []}
              year={year}
              onSelectWeek={setSelected}
              selectedWeek={selected}
            />
          </div>

          <fieldset className="m-0 flex shrink-0 flex-col gap-1 border-0 p-0">
            <legend className="sr-only">{t('weekly.year')}</legend>
            {years.map((y) => (
              <button
                key={y}
                type="button"
                onClick={() => setYear(y)}
                aria-pressed={y === year}
                className={cn(
                  'tabular rounded-md px-3 py-1 text-start text-xs transition-colors active:translate-y-px',
                  y === year
                    ? 'bg-accent font-medium text-white'
                    : 'text-ink-muted hover:bg-surface hover:text-ink',
                )}
              >
                {y}
              </button>
            ))}
          </fieldset>
        </div>
      </section>

      {/* Which week, and when the machine mails this one on its own. */}
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <PeriodPicker mode="week" value={selected} onChange={setSelected} />
        <NextRun kind="weekly" />
      </div>

      {genError && <ErrorState message={genError} onRetry={generate} />}

      {content && (
        <ReportEditor
          kind="weekly"
          period={label}
          objet={content.objet}
          corps={content.corps}
          image={image}
          generatedBy={content.generated_by}
          figures={{
            rapports: week.rows.length,
            techniciens: week.techniciens,
            chantiers: week.chantiers,
            flagged: week.flagged,
            goulottes: week.totals.goulottes,
            cables: week.totals.cables,
            bureaux: week.totals.bureaux,
            panneaux: week.totals.panneaux,
          }}
          byTech={week.byTech.map(([name, v]) => ({ name, ...v }))}
        />
      )}

      {week.rows.length === 0 ? (
        <EmptyState
          icon={CalendarBlankIcon}
          title={t('weekly.emptyTitle', { range: rangeLabel })}
          body={t('weekly.emptyBody')}
          // Same reasoning as the Daily page: no rows means nothing to generate
          // from, so the way out is the last week that has data, not a greyed
          // primary button.
          action={
            lastWeekWithData && (
              <button
                type="button"
                onClick={() => setSelected(lastWeekWithData)}
                className="border-line text-ink hover:bg-surface inline-flex items-center gap-2 rounded-md border px-3.5 py-2 text-sm transition-colors active:translate-y-px"
              >
                <ArrowUUpLeftIcon size={14} />
                {t('weekly.goLastWeek')}
              </button>
            )
          }
        />
      ) : (
        <>
          <div className="flex flex-wrap gap-x-12 gap-y-6">
            {[
              [fmt.format(week.rows.length), t('metric.total')],
              [fmt.format(week.techniciens), t('metric.techniciens')],
              [fmt.format(week.chantiers), t('weekly.chantiers')],
              [fmt.format(week.flagged), t('metric.flagged')],
            ].map(([v, l]) => (
              <div key={l}>
                <p className="tabular text-ink text-3xl leading-none font-medium">{v}</p>
                <p className="text-ink-faint mt-1.5 text-xs">{l}</p>
              </div>
            ))}
          </div>

          <section className="flex flex-col gap-4">
            <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
              {t('weekly.perDay')}
            </h2>
            <div className="grid grid-cols-7 gap-2">
              {week.perDay.map((rows, i) => (
                <div key={iso(days[i])} className="flex flex-col items-center gap-2">
                  <div className="flex h-24 w-full items-end">
                    <motion.div
                      className="bg-accent w-full rounded-t-[4px]"
                      initial={{ height: 0 }}
                      animate={{ height: `${(rows.length / maxDay) * 100}%` }}
                      transition={{ type: 'spring', stiffness: 100, damping: 20, delay: i * 0.04 }}
                    />
                  </div>
                  <span className="tabular text-ink text-xs">{rows.length}</span>
                  <span className="text-ink-faint text-[0.6875rem] capitalize">
                    {dayName.format(days[i])}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
              {t('panel.productionToday')}
            </h2>
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
              {[
                [fmt.format(week.totals.goulottes), t('metric.goulottes'), 'm'],
                [fmt.format(week.totals.cables), t('metric.cables'), 'm'],
                [fmt.format(week.totals.bureaux), t('metric.bureaux'), ''],
                [fmt.format(week.totals.panneaux), t('metric.panneaux'), ''],
              ].map(([v, l, u]) => (
                <div key={l}>
                  <p className="tabular text-ink text-2xl leading-none font-medium">
                    {v}
                    {u && <span className="text-ink-faint ms-1 text-xs">{u}</span>}
                  </p>
                  <p className="text-ink-faint mt-2 text-xs">{l}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
              {t('weekly.perTech')}
            </h2>
            <ul className="divide-line flex flex-col divide-y">
              {week.byTech.map(([name, v]) => (
                <li key={name} className="flex items-baseline gap-4 py-2.5 first:pt-0 last:pb-0">
                  <span className="text-ink min-w-0 flex-1 truncate text-sm">{name}</span>
                  <span className="tabular text-ink-muted text-sm">{fmt.format(v.count)}</span>
                  <span className="tabular text-ink-faint w-20 text-end text-xs">
                    {fmt.format(v.goulottes)} m
                  </span>
                  <span className="tabular text-status-warn w-8 text-end text-xs">
                    {v.flagged || ''}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <ReportImageCard
            rows={week.rows}
            title={t('image.weekTitle', { start: iso(days[0]), end: iso(days[6]) })}
            disabled={week.rows.length === 0}
            onImage={setImage}
          />
        </>
      )}
    </motion.div>
  )
}
