import { useMemo } from 'react'
import { motion } from 'motion/react'
import { api, pickReceptionWorkflow, useApi } from '@/lib/api'
import { computeMetrics, formatUptime, isFlagged, minutesOf } from '@/lib/metrics'
import { buildServices } from '@/lib/services'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { Masthead, type SystemState } from '@/components/masthead'
import { DayRibbon, type Tick } from '@/components/day-ribbon'
import { ServicesPanel } from '@/components/services-panel'
import { ContributionGraph } from '@/components/contribution-graph'

const rise = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 100, damping: 20 } },
}

/** Section heading. No box: a rule and a label carry the grouping. */
function Band({ title, aside, children }: { title: string; aside?: string; children: React.ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col gap-4">
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

export function OverviewPage() {
  const { t, locale, dir } = useI18n()
  const { settings } = useSettings()
  const poll = settings.refreshMs || undefined

  const reports = useApi('reports', api.reports, poll)
  const health = useApi('health', api.health, poll)
  const logs = useApi('logs', api.logs, poll)
  const n8n = useApi('n8n', api.n8n, poll)
  const executions = useApi('n8n-executions', api.n8nExecutions, poll)

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

  const services = useMemo(
    () =>
      buildServices({
        health: health.data,
        healthError: health.error,
        logs: logs.data?.logs ?? [],
        stats: logs.data?.stats ?? null,
        logsError: logs.error,
        reportsOk: !reports.error,
        n8nReachable: n8n.data?.reachable ?? false,
        workflow: n8n.data ? pickReceptionWorkflow(n8n.data.workflows) : undefined,
        lastExecution: executions.data?.[0] ?? null,
        locale,
      }),
    [health.data, health.error, logs.data, logs.error, reports.error, n8n.data, executions.data, locale],
  )

  if (reports.error) return <ErrorState message={reports.error} onRetry={reports.reload} />

  if (reports.loading || !m) {
    return (
      <div className="flex flex-col gap-10 pt-8">
        <Skeleton className="h-44 rounded-xl" />
        <div className="grid gap-10 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
        <Skeleton className="h-48" />
      </div>
    )
  }

  if (m.total === 0) return <EmptyState />

  const apiUp = !health.error && health.data?.status === 'ok'
  const anyServiceDown = services.some((s) => s.state === 'fail')
  // Degraded is a real state, not a cosmetic one: something answers but needs a human.
  const state: SystemState = !apiUp || anyServiceDown ? (apiUp ? 'degraded' : 'down') : m.flagged > 0 ? 'degraded' : 'nominal'

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

      {/* Ribbon and totals share a row: the same day, read two ways. */}
      <motion.div variants={rise} className="grid gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Band
          title={t('ribbon.title')}
          aside={m.dayISO ? `${m.dayISO}${m.dayIsStale ? ` · ${t('ribbon.stale')}` : ''}` : undefined}
        >
          <DayRibbon ticks={ticks} dir={dir} />
        </Band>

        <Band title={t('panel.productionToday')} aside={fmt.format(m.dayRows.length)}>
          <div className="grid grid-cols-2 gap-x-6 gap-y-5">
            <Quantity value={fmt.format(m.totalsToday.goulottes_m)} label={t('metric.goulottes')} unit="m" />
            <Quantity value={fmt.format(m.totalsToday.cables_m)} label={t('metric.cables')} unit="m" />
            <Quantity value={fmt.format(m.totalsToday.bureaux)} label={t('metric.bureaux')} />
            <Quantity value={fmt.format(m.totalsToday.panneaux)} label={t('metric.panneaux')} />
          </div>
        </Band>
      </motion.div>

      <motion.div variants={rise}>
        <Band title={t('graph.year')} aside={fmt.format(m.total)}>
          <ContributionGraph rows={reports.data?.reports ?? []} />
        </Band>
      </motion.div>

      <motion.div variants={rise} className="grid gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        {/* The aside states the coverage limit: this history is observed from
            this screen only, so gaps mean "unwatched", not "down". */}
        <Band title={t('panel.services')} aside={t('panel.uptimeNote')}>
          <ServicesPanel rows={services} />
        </Band>

        <Band title={t('panel.quality')}>
          <div className="grid grid-cols-2 gap-x-6 gap-y-5">
            <Quantity value={fmt.format(m.flagged)} label={t('metric.flagged')} />
            <Quantity value={m.voiceShare !== null ? `${m.voiceShare}%` : '—'} label={t('metric.voiceShare')} />
            <Quantity
              value={fmt.format(logs.data?.stats.last_24h.error ?? 0)}
              label={t('metric.errors24h')}
            />
            <Quantity
              value={fmt.format(logs.data?.stats.pending_sheet_writes ?? 0)}
              label={t('metric.pendingWrites')}
            />
          </div>
          {m.undated > 0 && (
            <p className="text-status-warn mt-2 text-xs">
              {t('metric.undated')}: <span className="tabular">{fmt.format(m.undated)}</span>
            </p>
          )}
        </Band>
      </motion.div>
    </motion.div>
  )
}
