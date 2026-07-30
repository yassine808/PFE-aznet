import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { CopyIcon, DownloadSimpleIcon, SparkleIcon } from '@phosphor-icons/react'
import { cn } from '@/lib/utils'
import { api, generateDailyReport, useApi, type DailyReportContent } from '@/lib/api'
import { exportReport, type ReportFormat } from '@/lib/report-export'
import { isFlagged, num, toISODate } from '@/lib/metrics'
import { useI18n } from '@/lib/i18n'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { ContributionGraph, isoOf as iso, weekStart } from '@/components/contribution-graph'

const DAY_MS = 86_400_000

export function WeeklyReportPage() {
  const { t, locale } = useI18n()
  const reports = useApi('reports', api.reports)
  // Selected week as its Monday. Picked from the year graph below.
  const [selected, setSelected] = useState(() => iso(weekStart(new Date())))
  const [year, setYear] = useState(() => new Date().getFullYear())
  const [copied, setCopied] = useState(false)
  const [content, setContent] = useState<DailyReportContent | null>(null)
  const [busy, setBusy] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  const settings = useApi('settings', api.settings)
  const format = (settings.data?.settings.report_format ?? 'markdown') as ReportFormat

  const fmt = useMemo(
    () => new Intl.NumberFormat(locale === 'ar' ? 'ar-MA' : locale === 'en' ? 'en-GB' : 'fr-FR'),
    [locale],
  )
  const dayName = useMemo(
    () =>
      new Intl.DateTimeFormat(locale === 'ar' ? 'ar-MA' : locale === 'en' ? 'en-GB' : 'fr-FR', {
        weekday: 'short',
      }),
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
      setContent(await generateDailyReport(`${iso(days[0])} → ${iso(days[6])}`, week.rows))
    } catch (err) {
      setGenError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const copy = async () => {
    const lines = [
      `${t('weekly.title')} ${iso(days[0])} → ${iso(days[6])}`,
      '',
      `${t('metric.total')}: ${week.rows.length}`,
      `${t('metric.techniciens')}: ${week.techniciens}`,
      `${t('weekly.chantiers')}: ${week.chantiers}`,
      `${t('metric.flagged')}: ${week.flagged}`,
      '',
      `${t('metric.goulottes')}: ${week.totals.goulottes} m`,
      `${t('metric.cables')}: ${week.totals.cables} m`,
      `${t('metric.bureaux')}: ${week.totals.bureaux}`,
      `${t('metric.panneaux')}: ${week.totals.panneaux}`,
      '',
      ...week.byTech.map(([name, v]) => `- ${name}: ${v.count} (${v.goulottes} m)`),
    ]
    await navigator.clipboard.writeText(lines.join('\n'))
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }

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
      <div className="flex flex-wrap items-center gap-3">
        <span className="tabular text-ink text-sm">
          {iso(days[0])} → {iso(days[6])}
        </span>
        <div className="ms-auto flex items-center gap-3">
          <button
            type="button"
            onClick={generate}
            disabled={busy || week.rows.length === 0}
            className={cn(
              'flex items-center gap-2 text-xs transition-transform',
              busy || week.rows.length === 0
                ? 'border-line text-ink-faint cursor-not-allowed rounded-md border px-3 py-1.5'
                : 'bg-accent breathe-glow rounded-md px-3.5 py-2 text-white active:translate-y-px',
            )}
          >
            <SparkleIcon size={13} weight="fill" />
            {busy ? t('daily.generating') : t('daily.generate')}
          </button>

          {content && (
            <button
              type="button"
              onClick={() => void exportReport(content.objet, content.corps, format)}
              className="border-line text-ink-muted hover:text-ink flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors active:translate-y-px"
            >
              <DownloadSimpleIcon size={13} />
              {t('daily.download')}
            </button>
          )}

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

      {genError && <ErrorState message={genError} onRetry={generate} />}

      {content && (
        <section className="border-line rounded-xl border p-6">
          <p className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
            {t('daily.subject')}
          </p>
          <h2 className="text-ink mt-1 text-lg font-medium tracking-tight">{content.objet}</h2>
          <p className="text-ink mt-4 max-w-[70ch] text-sm leading-relaxed whitespace-pre-wrap">
            {content.corps}
          </p>
        </section>
      )}

      {/* Pick a week by clicking its column. One year at a time; the rail on the
          right switches years, the way GitHub's contribution calendar does. */}
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

          <div className="flex shrink-0 flex-col gap-1" role="group" aria-label={t('weekly.year')}>
            {years.map((y) => (
              <button
                key={y}
                type="button"
                onClick={() => setYear(y)}
                aria-pressed={y === year}
                className={cn(
                  'tabular rounded-md px-4 py-1.5 text-start text-sm transition-colors active:translate-y-px',
                  y === year
                    ? 'bg-accent font-medium text-white'
                    : 'text-ink-muted hover:bg-surface hover:text-ink',
                )}
              >
                {y}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Computed locally from the Sheet: no model call, so the numbers are arithmetic, not prose. */}
      <p className="text-ink-faint max-w-[65ch] text-sm">{t('weekly.intro')}</p>

      {week.rows.length === 0 ? (
        <EmptyState body={t('weekly.noRows')} />
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
                <div key={i} className="flex flex-col items-center gap-2">
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
        </>
      )}
    </motion.div>
  )
}
