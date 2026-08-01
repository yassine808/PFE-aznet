import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { CopyIcon, DownloadSimpleIcon, SparkleIcon } from '@phosphor-icons/react'
import { api, generateDailyReport, useApi, type DailyReportContent } from '@/lib/api'
import { exportReport, type ReportFormat } from '@/lib/report-export'
import { isFlagged, num, toISODate, todayISO } from '@/lib/metrics'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { ActivityGraphSection } from '@/components/activity-graph-section'

export function DailyReportPage() {
  const { t, locale } = useI18n()
  const reports = useApi('reports', api.reports)

  const [date, setDate] = useState(todayISO())
  const [content, setContent] = useState<DailyReportContent | null>(null)
  // Format preference comes from the Automation panel; markdown until it loads.
  const settings = useApi('settings', api.settings)
  const format = (settings.data?.settings.report_format ?? 'markdown') as ReportFormat
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const fmt = useMemo(() => new Intl.NumberFormat(intlLocaleOf(locale)), [locale])

  const rows = useMemo(
    () => (reports.data?.reports ?? []).filter((r) => toISODate(r.date) === date),
    [reports.data, date],
  )

  // Same aggregates as the weekly page, for the one chosen day — arithmetic,
  // not prose, so the model call stays reserved for the report itself.
  const stats = useMemo(() => {
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
      totals,
      byTech: [...byTech.entries()].sort((a, b) => b[1].count - a[1].count),
      flagged: rows.filter((r) => isFlagged(r.flag_review)).length,
      techniciens: new Set(rows.map((r) => (r.technicien ?? '').trim()).filter(Boolean)).size,
      chantiers: new Set(rows.map((r) => (r.chantier ?? '').trim()).filter(Boolean)).size,
    }
  }, [rows])

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

      <ActivityGraphSection rows={reports.data?.reports ?? []} date={date} onSelectDay={setDate} />

      {error && <ErrorState message={error} onRetry={generate} />}

      {rows.length === 0 && !error && <EmptyState body={t('daily.noRows')} />}

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

          <section className="flex flex-col gap-4">
            <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
              {t('panel.productionToday')}
            </h2>
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
              {[
                [fmt.format(stats.totals.goulottes), t('metric.goulottes'), 'm'],
                [fmt.format(stats.totals.cables), t('metric.cables'), 'm'],
                [fmt.format(stats.totals.bureaux), t('metric.bureaux'), ''],
                [fmt.format(stats.totals.panneaux), t('metric.panneaux'), ''],
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
              {stats.byTech.map(([name, v]) => (
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
        </>
      )}

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
          {/* Provenance: manual runs are signed with the account that asked, so
              an emailed report and a panel report are never confused. */}
          <p className="text-ink-faint mt-3 text-xs">
            {content.generated_by && content.generated_by !== 'automatique'
              ? t('daily.generatedBy', { name: content.generated_by })
              : t('daily.generatedAuto')}
          </p>
          {/* Preserve the model's paragraph breaks; it writes prose, not markup. */}
          <p className="text-ink mt-4 max-w-[70ch] text-sm leading-relaxed whitespace-pre-wrap">
            {content.corps}
          </p>
        </motion.article>
      )}
    </motion.div>
  )
}
