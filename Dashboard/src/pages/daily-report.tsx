import { useEffect, useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { ArrowUUpLeftIcon, FileTextIcon } from '@phosphor-icons/react'
import { api, generateDailyReport, useApi } from '@/lib/api'
import { parseISODay, toISODate, todayISO } from '@/lib/metrics'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { useHeaderAction } from '@/lib/page-header'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { ActivityGraphSection } from '@/components/activity-graph-section'
import { GenerateButton } from '@/components/generate-button'
import { NextRun } from '@/components/next-run'
import { PeriodPicker } from '@/components/period-picker'
import { LastReportDocx } from '@/components/last-report-docx'
import { computeReportStats } from '@/lib/report-stats'

export function DailyReportPage({ initialDate }: { readonly initialDate?: string }) {
  const { t, locale } = useI18n()
  const reports = useApi('reports', api.reports)

  // `#/daily?date=2026-08-05` — the target of the report mail's button. Only
  // the initial value: once the page is open the picker owns the date, so a
  // stale link cannot fight the operator for control of it.
  const [date, setDate] = useState(initialDate || todayISO())
  // What Générer produces is a stored version, document and all — not a text
  // this page holds on to. Bumping the token is how the panel below learns to
  // go and fetch it; there is no draft in this component any more, and so
  // nothing that can silently disagree with what the API stored.
  const [reloadToken, setReloadToken] = useState(0)
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
    try {
      await generateDailyReport(date, rows)
      setReloadToken((n) => n + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  // A different day means a different report, and a failed generate for the old
  // day must not follow it over.
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
      )}

      {/* The document that was actually produced for this day, in place of the
          two panels that used to sit here and of the text editor that used to
          appear under them after Générer. Those recomputed in the browser what
          the report already states, in a different shape — so a manager
          comparing the page with the Word file in their inbox was comparing two
          renderings of one day with no way to know which one the director read.
          The report is the artefact; the tiles above are its index, and
          correcting it happens on the Reports page, where a report is chosen
          from the list rather than from a date picker. */}
      <LastReportDocx kind="daily" period={date} reloadToken={reloadToken}
        editHref={`#/reports?period=${encodeURIComponent(date)}`}
      />

    </motion.div>
  )
}
