import { useEffect, useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { ArrowUUpLeftIcon, FileTextIcon } from '@phosphor-icons/react'
import {
  api,
  generateDailyReport,
  useApi,
  type DailyReportContent,
} from '@/lib/api'
import { parseISODay, toISODate, todayISO } from '@/lib/metrics'
import { useAuth } from '@/lib/auth'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { useHeaderAction } from '@/lib/page-header'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { ActivityGraphSection } from '@/components/activity-graph-section'
import { GenerateButton } from '@/components/generate-button'
import { NextRun } from '@/components/next-run'
import { PeriodPicker } from '@/components/period-picker'
import { ReportEditor } from '@/components/report-editor'
import { ReportPerTech, ReportTotals } from '@/components/report-panels'
import { computeReportStats } from '@/lib/report-stats'

export function DailyReportPage({ initialDate }: { readonly initialDate?: string }) {
  const { t, locale } = useI18n()
  const { user } = useAuth()
  const reports = useApi('reports', api.reports)

  // `#/daily?date=2026-08-05` — the target of the report mail's button. Only
  // the initial value: once the page is open the picker owns the date, so a
  // stale link cannot fight the operator for control of it.
  const [date, setDate] = useState(initialDate || todayISO())
  const [content, setContent] = useState<DailyReportContent | null>(null)
  // The day the report was generated for, frozen at generate time. The editor
  // is keyed to this rather than to `date`: a draft deliberately survives a
  // picker switch (see the comment in report-editor.tsx), and labelling a
  // surviving Monday text with a Tuesday `period` would file it under the
  // wrong `report_versions` key on Save and diff it against the wrong history.
  const [contentPeriod, setContentPeriod] = useState<string | null>(null)
  // saves it with the version.
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fmt = useMemo(() => new Intl.NumberFormat(intlLocaleOf(locale)), [locale])

  // The chosen day as the reader's locale writes it — used by the empty state,
  // which has to name the day it is empty *for* to be worth more than "rien".
  const dayLabel = useMemo(() => {
    return new Intl.DateTimeFormat(intlLocaleOf(locale), {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    }).format(parseISODay(date))
  }, [date, locale])

  // The most recent day that actually has rows — the empty state's way out.
  // Carries its own formatted label: an ISO string in a button is a machine
  // talking, and the sentence right above it already says "5 août 2026".
  const lastDayWithData = useMemo(() => {
    let best: string | null = null
    for (const r of reports.data?.reports ?? []) {
      const d = toISODate(r.date)
      if (d && (best === null || d > best)) best = d
    }
    if (!best || best === date) return null
    const [y, m, d] = best.split('-').map(Number)
    return {
      iso: best,
      label: new Intl.DateTimeFormat(intlLocaleOf(locale), {
        day: 'numeric',
        month: 'long',
      }).format(new Date(y, m - 1, d)),
    }
  }, [reports.data, date, locale])

  const rows = useMemo(
    () => (reports.data?.reports ?? []).filter((r) => toISODate(r.date) === date),
    [reports.data, date],
  )

  // Same aggregates as the weekly page, for the one chosen day — arithmetic,
  // not prose, so the model call stays reserved for the report itself.
  const stats = useMemo(() => computeReportStats(rows), [rows])

  const generate = async () => {
    setBusy(true)
    setError(null)
    setContent(null)
    setContentPeriod(null)
    try {
      setContent(await generateDailyReport(date, rows))
      setContentPeriod(date)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  // A different day means a different report. The text is deliberately left
  // alone — the draft survives the switch (report-editor's documented intent)
  // — but a failed generate for the old day must not follow it over.
  useEffect(() => {
    setError(null)
  }, [date])

  // Generate sits beside the page title in the shared header, not on a second
  // line of its own — the title is already the widest thing on the page and the
  // one action belongs on it.
  useHeaderAction(<GenerateButton busy={busy} disabled={rows.length === 0} onClick={generate} />, [
    busy,
    rows.length,
    date,
    locale,
  ])

  if (reports.error) return <ErrorState message={reports.error} onRetry={reports.reload} />
  if (reports.loading) return <Skeleton className="mt-8 h-64 rounded-xl" />

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-6 pt-8"
    >
      <ActivityGraphSection rows={reports.data?.reports ?? []} date={date} onSelectDay={setDate} />

      {/* Which day, and when the machine sends this on its own — the two things
          the graph above cannot say for itself. */}
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <PeriodPicker mode="day" value={date} onChange={setDate} />
        <NextRun kind="daily" />
      </div>

      {error && <ErrorState message={error} onRetry={generate} />}

      {rows.length === 0 && !error && (
        <EmptyState
          icon={FileTextIcon}
          title={t('daily.emptyTitle', { date: dayLabel })}
          body={t('daily.emptyBody')}
          // Not a disabled "Générer" button: with no rows there is nothing to
          // generate *from*, and a greyed primary action in the middle of an
          // empty page is a dead end dressed up as a way out. The real way out
          // is the last day that has data, which the heatmap already knows.
          action={
            lastDayWithData && (
              <button
                type="button"
                onClick={() => setDate(lastDayWithData.iso)}
                className="border-line text-ink hover:bg-surface inline-flex items-center gap-2 rounded-md border px-3.5 py-2 text-sm transition-colors active:translate-y-px"
              >
                <ArrowUUpLeftIcon size={14} />
                {t('daily.goLastDay', { date: lastDayWithData.label })}
              </button>
            )
          }
        />
      )}

      {rows.length > 0 && (
        <>
          <div className="flex flex-wrap gap-x-12 gap-y-6">
            {[
              [fmt.format(rows.length), t('metric.total')],
              [fmt.format(stats.techniciens), t('metric.techniciens')],
              [fmt.format(stats.chantiers), t('weekly.chantiers')],
              [fmt.format(stats.flagged), t('metric.flagged')],
            ].map(([v, l]) => (
              <div key={l}>
                <p className="tabular text-ink text-3xl leading-none font-medium">{v}</p>
                <p className="text-ink-faint mt-1.5 text-xs">{l}</p>
              </div>
            ))}
          </div>

          <ReportTotals totals={stats.totals} />

          <ReportPerTech byTech={stats.byTech} />
        </>
      )}

      {content && (
        <ReportEditor
          kind="daily"
          period={contentPeriod ?? date}
          objet={content.objet}
          corps={content.corps}
          generatedBy={content.generated_by}
          // The history is keyed by whoever the report belongs to, and a run
          // started from this page is filed under the account that started it
          // — the same id `POST /daily-report` writes. Passing 0 here would
          // show an empty version list beside a report this page just
          // generated and archived.
          managerId={user?.id ?? 0}
        />
      )}
    </motion.div>
  )
}
