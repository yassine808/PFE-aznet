import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { CopyIcon, DownloadSimpleIcon, SparkleIcon } from '@phosphor-icons/react'
import { api, generateDailyReport, useApi, type DailyReportContent } from '@/lib/api'
import { exportReport, type ReportFormat } from '@/lib/report-export'
import { toISODate, todayISO } from '@/lib/metrics'
import { useI18n } from '@/lib/i18n'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { ContributionGraph } from '@/components/contribution-graph'

export function DailyReportPage() {
  const { t } = useI18n()
  const reports = useApi('reports', api.reports)

  const [date, setDate] = useState(todayISO())
  // Year shown by the graph. Follows the picked date, so typing a 2025 date in
  // the input scrolls the heatmap to 2025 rather than leaving it out of view.
  const year = Number(date.slice(0, 4)) || new Date().getFullYear()
  const years = useMemo(() => {
    const y = new Date().getFullYear()
    return [y, y - 1, y - 2]
  }, [])
  const [content, setContent] = useState<DailyReportContent | null>(null)
  // Format preference comes from the Automation panel; markdown until it loads.
  const settings = useApi('settings', api.settings)
  const format = (settings.data?.settings.report_format ?? 'markdown') as ReportFormat
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const daysWithData = useMemo(() => {
    const set = new Set<string>()
    for (const r of reports.data?.reports ?? []) {
      const iso = toISODate(r.date)
      if (iso) set.add(iso)
    }
    return [...set].sort().reverse()
  }, [reports.data])

  const rows = useMemo(
    () => (reports.data?.reports ?? []).filter((r) => toISODate(r.date) === date),
    [reports.data, date],
  )

  const generate = async () => {
    setBusy(true)
    setError(null)
    setContent(null)
    try {
      setContent(await generateDailyReport(date, rows))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const copy = async () => {
    if (!content) return
    await navigator.clipboard.writeText(`${content.objet}\n\n${content.corps}`)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }

  if (reports.error) return <ErrorState message={reports.error} onRetry={reports.reload} />
  if (reports.loading) return <Skeleton className="mt-8 h-64 rounded-xl" />

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-6 pt-8"
    >
      <p className="text-ink-faint max-w-[65ch] text-sm">{t('daily.intro')}</p>

      <div className="flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="report-date"
            className="text-ink-faint text-[0.6875rem] tracking-wide uppercase"
          >
            {t('daily.date')}
          </label>
          {/* Native date input: a picker library would be a dependency for zero gain. */}
          <input
            id="report-date"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="border-line focus:border-accent text-ink bg-canvas tabular rounded-md border px-3 py-2 text-sm outline-none transition-colors"
          />
        </div>

        <button
          type="button"
          onClick={generate}
          disabled={busy || rows.length === 0}
          className={
            busy || rows.length === 0
              ? 'border-line text-ink-faint cursor-not-allowed rounded-md border px-4 py-2 text-sm'
              : 'bg-accent breathe-glow rounded-md px-4 py-2 text-sm text-white transition-transform active:translate-y-px'
          }
        >
          <span className="flex items-center gap-2">
            <SparkleIcon size={14} weight="fill" />
            {busy ? t('daily.generating') : t('daily.generate')}
          </span>
        </button>

        <span className="tabular text-ink-faint pb-2 text-xs">
          {rows.length} {t('daily.rowsForDate')}
        </span>
      </div>

      {daysWithData.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
            {t('daily.available')}
          </span>
          {daysWithData.slice(0, 8).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDate(d)}
              className={`tabular rounded border px-2 py-1 text-xs transition-colors ${
                d === date
                  ? 'border-accent text-accent'
                  : 'border-line text-ink-faint hover:text-ink'
              }`}
            >
              {d}
            </button>
          ))}
        </div>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
          {t('graph.year')}
        </h2>

        <div className="flex items-start gap-5">
          <div className="min-w-0 flex-1">
            {/* Clicking a cell sets the report date; the date input stays authoritative. */}
            <ContributionGraph
              rows={reports.data?.reports ?? []}
              year={year}
              onSelectDay={setDate}
              selectedDay={date}
            />
          </div>

          <div className="flex shrink-0 flex-col gap-1" role="group" aria-label={t('weekly.year')}>
            {years.map((y) => (
              <button
                key={y}
                type="button"
                // Jump to Jan 1 of that year: the graph follows `date`, so the
                // year rail and the date input never disagree.
                onClick={() => setDate(`${y}-01-01`)}
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
          </div>
        </div>
      </section>

      {error && <ErrorState message={error} onRetry={generate} />}

      {rows.length === 0 && !error && <EmptyState body={t('daily.noRows')} />}

      {content && (
        <motion.article
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', stiffness: 100, damping: 20 }}
          className="border-line bg-surface edge rounded-xl border p-6"
        >
          <div className="border-line flex items-start justify-between gap-4 border-b pb-4">
            <div>
              <p className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
                {t('daily.subject')}
              </p>
              <h2 className="text-ink mt-1 text-lg font-medium tracking-tight">{content.objet}</h2>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => void exportReport(content.objet, content.corps, format)}
                className="border-line text-ink-muted hover:text-ink flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors active:translate-y-px"
              >
                <DownloadSimpleIcon size={13} />
                {t('daily.download')}
              </button>
              <button
                type="button"
                onClick={copy}
                className="border-line text-ink-muted hover:text-ink flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors active:translate-y-px"
              >
                <CopyIcon size={13} />
                {copied ? t('daily.copied') : t('daily.copy')}
              </button>
            </div>
          </div>
          {/* Preserve the model's paragraph breaks; it writes prose, not markup. */}
          <p className="text-ink mt-4 max-w-[70ch] text-sm leading-relaxed whitespace-pre-wrap">
            {content.corps}
          </p>
        </motion.article>
      )}
    </motion.div>
  )
}
