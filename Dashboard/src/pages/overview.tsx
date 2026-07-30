import { useMemo } from 'react'
import { motion } from 'motion/react'
import { api, useApi } from '@/lib/api'
import { computeMetrics, formatUptime, isFlagged, minutesOf } from '@/lib/metrics'
import { useOps } from '@/lib/ops-context'
import { useI18n } from '@/lib/i18n'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { Masthead, type SystemState } from '@/components/masthead'
import { DayRibbon, type Tick } from '@/components/day-ribbon'
import { ServicesPanel } from '@/components/services-panel'
import { ContributionGraph } from '@/components/contribution-graph'

const rise = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 100, damping: 20 } },
}

/** Section heading. No box: a rule and a label carry the grouping. */
function Band({
  title,
  aside,
  children,
}: {
  title: string
  aside?: string
  children: React.ReactNode
}) {
  return (
    <section className="flex min-w-0 flex-col gap-3">
      <div className="border-line flex items-baseline justify-between gap-3 border-b pb-1.5">
        <h2 className="text-ink-faint text-[0.6875rem] font-medium tracking-wide uppercase">
          {title}
        </h2>
        {aside && <span className="tabular text-ink-faint text-[0.6875rem]">{aside}</span>}
      </div>
      {children}
    </section>
  )
}

function Quantity({ value, label, unit }: { value: string; label: string; unit?: string }) {
  return (
    <div>
      <p className="tabular text-ink text-xl leading-none font-medium">
        {value}
        {unit && <span className="text-ink-faint ms-1 text-[0.6875rem]">{unit}</span>}
      </p>
      <p className="text-ink-faint mt-1.5 text-[0.6875rem]">{label}</p>
    </div>
  )
}

export function OverviewPage({ onOpenDay }: { onOpenDay: (iso: string) => void }) {
  const { t, dir, locale } = useI18n()
  const { services, health, healthError, stats } = useOps()
  const reports = useApi('reports', api.reports)

  const m = useMemo(
    () => (reports.data ? computeMetrics(reports.data.reports) : null),
    [reports.data],
  )
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
          : {
              at,
              flagged: isFlagged(r.flag_review),
              time: r.heure ?? '',
              technicien: r.technicien ?? '',
              chantier: r.chantier ?? '',
            }
      })
      .filter((x): x is Tick => x !== null)
  }, [m])

  if (reports.error) return <ErrorState message={reports.error} onRetry={reports.reload} />

  if (reports.loading || !m) {
    return (
      <div className="flex flex-col gap-5 pt-5">
        <Skeleton className="h-32 rounded-xl" />
        <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
        <Skeleton className="h-40" />
      </div>
    )
  }

  if (m.total === 0) return <EmptyState />

  const apiUp = !healthError && health?.status === 'ok'
  const anyDown = services.some((s) => s.state === 'fail')
  const state: SystemState = !apiUp ? 'down' : anyDown || m.flagged > 0 ? 'degraded' : 'nominal'

  return (
    <motion.div
      variants={{ show: { transition: { staggerChildren: 0.05 } } }}
      initial="hidden"
      animate="show"
      className="flex flex-col gap-5 pt-5"
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
            { label: t('metric.errors24h'), value: fmt.format(stats?.last_24h.error ?? 0) },
            {
              label: t('metric.uptime'),
              value: health ? formatUptime(health.uptime_seconds) : '—',
            },
          ]}
        />
      </motion.div>

      {/* Ribbon and totals share a row: the same day, read two ways. */}
      <motion.div
        variants={rise}
        className="grid gap-x-8 gap-y-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]"
      >
        <Band
          title={t('ribbon.title')}
          aside={
            m.dayISO ? `${m.dayISO}${m.dayIsStale ? ` · ${t('ribbon.stale')}` : ''}` : undefined
          }
        >
          <DayRibbon ticks={ticks} dir={dir} />
        </Band>

        <Band title={t('panel.productionToday')} aside={fmt.format(m.dayRows.length)}>
          <div className="grid grid-cols-2 gap-x-5 gap-y-4">
            <Quantity
              value={fmt.format(m.totalsToday.goulottes_m)}
              label={t('metric.goulottes')}
              unit="m"
            />
            <Quantity
              value={fmt.format(m.totalsToday.cables_m)}
              label={t('metric.cables')}
              unit="m"
            />
            <Quantity value={fmt.format(m.totalsToday.bureaux)} label={t('metric.bureaux')} />
            <Quantity value={fmt.format(m.totalsToday.panneaux)} label={t('metric.panneaux')} />
          </div>
        </Band>
      </motion.div>

      <motion.div
        variants={rise}
        className="grid gap-x-8 gap-y-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"
      >
        {/* The aside states the coverage limit: this history is observed from
            this screen only, so gaps mean "unwatched", not "down". */}
        <Band title={t('panel.services')} aside={t('panel.uptimeNote')}>
          <ServicesPanel rows={services} />
        </Band>

        <Band title={t('graph.year')} aside={fmt.format(m.total)}>
          {/* Clicking a day deep-links into the Inbox filtered to that date. */}
          <ContributionGraph rows={reports.data?.reports ?? []} onSelectDay={onOpenDay} />
        </Band>
      </motion.div>
    </motion.div>
  )
}
