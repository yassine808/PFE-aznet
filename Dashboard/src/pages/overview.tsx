import { useMemo } from 'react'
import { motion } from 'motion/react'
import { FlagIcon } from '@phosphor-icons/react'
import { api, useApi, type ReportRow } from '@/lib/api'
import { computeMetrics, formatUptime, isFlagged, minutesOf, num } from '@/lib/metrics'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { Masthead, type SystemState } from '@/components/masthead'
import { DayRibbon, type Tick } from '@/components/day-ribbon'
import { cn } from '@/lib/utils'

const rise = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 100, damping: 20 } },
}

/** Section heading. No box: a rule and a label carry the grouping. */
function Band({ title, aside, children }: { title: string; aside?: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <div className="border-line flex items-baseline justify-between gap-4 border-b pb-2">
        <h2 className="text-ink-faint text-[0.6875rem] font-medium tracking-wide uppercase">{title}</h2>
        {aside && <span className="tabular text-ink-faint text-xs">{aside}</span>}
      </div>
      {children}
    </section>
  )
}

function Quantity({ value, label, unit }: { value: string; label: string; unit?: string }) {
  return (
    <div className="py-1">
      <p className="tabular text-ink text-2xl leading-none font-medium">
        {value}
        {unit && <span className="text-ink-faint ms-1 text-xs">{unit}</span>}
      </p>
      <p className="text-ink-faint mt-2 text-xs">{label}</p>
    </div>
  )
}

function LedgerRow({
  r,
  fmt,
  threshold,
  pad,
}: {
  r: ReportRow
  fmt: Intl.NumberFormat
  threshold: number
  pad: string
}) {
  const flagged = isFlagged(r.flag_review)
  const confidence = num(r.confidence)

  return (
    <tr className="border-line hover:bg-surface border-b transition-colors last:border-b-0">
      <td className={cn('tabular text-ink-faint pe-4 align-top text-xs whitespace-nowrap', pad)}>
        {r.date}
        <span className="ms-2 opacity-70">{r.heure}</span>
      </td>
      <td className={cn('text-ink pe-4 align-top text-sm whitespace-nowrap', pad)}>{r.technicien || '—'}</td>
      <td className={cn('text-ink-muted pe-4 align-top text-sm', pad)}>{r.chantier || '—'}</td>
      <td className={cn('tabular text-ink pe-4 text-end align-top text-sm whitespace-nowrap', pad)}>
        {num(r.goulottes_m) ? fmt.format(num(r.goulottes_m)) : '·'}
      </td>
      <td className={cn('tabular text-ink pe-4 text-end align-top text-sm whitespace-nowrap', pad)}>
        {num(r.cables_m) ? fmt.format(num(r.cables_m)) : '·'}
      </td>
      <td className={cn('pe-4 align-top', pad)}>
        {/* Confidence as a bar, not a percentage: the eye compares lengths faster than digits. */}
        <span className="bg-line inline-block h-1 w-14 overflow-hidden rounded-full align-middle">
          <span
            className={cn('block h-full rounded-full', confidence < threshold ? 'bg-status-warn' : 'bg-status-ok')}
            style={{ width: `${Math.round(Math.min(Math.max(confidence, 0), 1) * 100)}%` }}
          />
        </span>
      </td>
      <td className="py-3 align-top">
        {flagged && <FlagIcon size={14} weight="fill" className="text-status-warn" />}
      </td>
    </tr>
  )
}

export function OverviewPage() {
  const { t, locale, dir } = useI18n()
  const { settings } = useSettings()
  // 0 means manual only: useApi treats a falsy interval as "fetch once".
  const reports = useApi(api.reports, settings.refreshMs || undefined)
  const health = useApi(api.health, settings.refreshMs ? Math.min(settings.refreshMs, 30_000) : undefined)

  const m = useMemo(() => (reports.data ? computeMetrics(reports.data.reports) : null), [reports.data])
  const fmt = useMemo(
    () => new Intl.NumberFormat(locale === 'ar' ? 'ar-MA' : locale === 'en' ? 'en-GB' : 'fr-FR'),
    [locale],
  )

  const ticks: Tick[] = useMemo(() => {
    if (!m) return []
    return m.dayRows
      .map((r) => {
        const at = minutesOf(r.heure)
        return at === null
          ? null
          : { at, flagged: isFlagged(r.flag_review), label: `${r.heure} · ${r.technicien ?? ''}` }
      })
      .filter((x): x is Tick => x !== null)
  }, [m])

  if (reports.error) return <ErrorState message={reports.error} onRetry={reports.reload} />

  if (reports.loading || !m) {
    return (
      <div className="flex flex-col gap-10 pt-8">
        <Skeleton className="h-44 rounded-xl" />
        <Skeleton className="h-24" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  if (m.total === 0) return <EmptyState />

  const apiUp = !health.error && health.data?.status === 'ok'
  // Degraded is a real state, not a cosmetic one: the API answers but rows need a human.
  const state: SystemState = !apiUp ? 'down' : m.flagged > 0 ? 'degraded' : 'nominal'

  return (
    <motion.div
      variants={{ show: { transition: { staggerChildren: 0.06 } } }}
      initial="hidden"
      animate="show"
      className="flex flex-col gap-10 pt-8"
    >
      <motion.div variants={rise}>
        <Masthead
          state={state}
          headline={fmt.format(m.today)}
          headlineLabel={t('metric.today')}
          meta={[
            { label: t('metric.week'), value: fmt.format(m.week) },
            { label: t('metric.flagged'), value: fmt.format(m.flagged) },
            { label: t('metric.techniciens'), value: fmt.format(m.techniciens) },
            { label: t('metric.uptime'), value: health.data ? formatUptime(health.data.uptime_seconds) : '—' },
          ]}
        />
      </motion.div>

      {health.error && (
        <motion.div variants={rise}>
          <ErrorState message={health.error} onRetry={health.reload} />
        </motion.div>
      )}

      <motion.div variants={rise}>
        <Band
          title={t('ribbon.title')}
          aside={m.dayISO ? `${m.dayISO}${m.dayIsStale ? ` · ${t('ribbon.stale')}` : ''}` : undefined}
        >
          <DayRibbon ticks={ticks} dir={dir} />
        </Band>
      </motion.div>

      <motion.div variants={rise}>
        <Band title={t('panel.productionToday')} aside={m.dayISO ?? undefined}>
          <div className="divide-line grid grid-cols-2 gap-x-8 sm:grid-cols-4 sm:divide-x">
            <Quantity value={fmt.format(m.totalsToday.goulottes_m)} label={t('metric.goulottes')} unit="m" />
            <Quantity value={fmt.format(m.totalsToday.cables_m)} label={t('metric.cables')} unit="m" />
            <Quantity value={fmt.format(m.totalsToday.bureaux)} label={t('metric.bureaux')} />
            <Quantity value={fmt.format(m.totalsToday.panneaux)} label={t('metric.panneaux')} />
          </div>
        </Band>
      </motion.div>

      <motion.div variants={rise}>
        <Band title={t('ledger.title')} aside={`${fmt.format(m.ledger.length)} · ${t('metric.total').toLowerCase()}`}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[46rem] border-collapse text-start">
              <thead>
                <tr className="border-line text-ink-faint border-b text-start text-[0.6875rem] tracking-wide uppercase">
                  <th className="py-2 pe-4 text-start font-medium">{t('col.when')}</th>
                  <th className="py-2 pe-4 text-start font-medium">{t('col.technicien')}</th>
                  <th className="py-2 pe-4 text-start font-medium">{t('col.chantier')}</th>
                  <th className="py-2 pe-4 text-end font-medium">{t('metric.goulottes')}</th>
                  <th className="py-2 pe-4 text-end font-medium">{t('metric.cables')}</th>
                  <th className="py-2 pe-4 text-start font-medium">{t('col.confidence')}</th>
                  <th className="py-2 text-start font-medium sr-only">{t('metric.flagged')}</th>
                </tr>
              </thead>
              <tbody>
                {m.ledger.map((r) => (
                  <LedgerRow
                    key={r._row}
                    r={r}
                    fmt={fmt}
                    threshold={settings.confidence}
                    pad={settings.density === 'compact' ? 'py-1.5' : 'py-3'}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {m.undated > 0 && (
            <p className="text-status-warn text-xs">
              {t('metric.undated')}: <span className="tabular">{fmt.format(m.undated)}</span>
            </p>
          )}
        </Band>
      </motion.div>
    </motion.div>
  )
}
