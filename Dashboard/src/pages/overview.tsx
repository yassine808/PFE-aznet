import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { WarningIcon } from '@phosphor-icons/react'
import { api, deleteChantier, useApi, verifyChantier } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { computeMetrics, formatUptime, isFlagged, minutesOf } from '@/lib/metrics'
import { useOps } from '@/lib/ops-context'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
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
  readonly title: string
  readonly aside?: string
  readonly children: React.ReactNode
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

function Quantity({
  value,
  label,
  unit,
}: {
  readonly value: string
  readonly label: string
  readonly unit?: string
}) {
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

/**
 * Sites the pipeline invented from a spoken name nobody has confirmed.
 *
 * It lives on the Overview because that is the one page a director opens
 * without being sent there: an unverified site is silent otherwise, and a
 * mis-transcription left alone becomes a permanent tab in his own file — the
 * extra sheets he already objected to, arriving by another door. Renders
 * nothing while the list is clean, so the page is unchanged on a normal day.
 */
function UnverifiedSites() {
  const { t } = useI18n()
  const { user } = useAuth()
  const chantiers = useApi('chantiers', api.chantiers)
  const [busy, setBusy] = useState<number | null>(null)
  // Deleting drops the bordereau with the site, so it takes a second click.
  const [armed, setArmed] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const pending = (chantiers.data?.chantiers ?? []).filter((c) => c.verifie === false)
  if (pending.length === 0) return null

  const act = (id: number, fn: (id: number) => Promise<void>) => async () => {
    setBusy(id)
    setError(null)
    try {
      await fn(id)
      chantiers.reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
      setArmed(null)
    }
  }

  return (
    <motion.div variants={rise}>
      <Band title={t('chantiers.unverified')} aside={String(pending.length)}>
        <p className="text-ink-muted max-w-[70ch] text-xs leading-relaxed">
          {t('chantiers.unverifiedIntro')}
        </p>
        <ul className="mt-1 flex flex-col gap-2">
          {pending.map((c) => (
            <li
              key={c.id}
              className="border-line flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2"
            >
              <span className="text-ink flex min-w-0 items-center gap-2 text-sm">
                <WarningIcon size={14} className="text-status-warn shrink-0" />
                <span className="truncate">{c.nom}</span>
              </span>
              {user?.role === 'directeur' && (
                <span className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={busy === c.id}
                    onClick={act(c.id, verifyChantier)}
                    className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent cursor-pointer rounded-md border px-2.5 py-1 text-xs transition-colors outline-none focus-visible:ring-2 disabled:opacity-50"
                  >
                    {t('chantiers.confirm')}
                  </button>
                  <button
                    type="button"
                    disabled={busy === c.id}
                    onClick={
                      armed === c.id ? act(c.id, deleteChantier) : () => setArmed(c.id)
                    }
                    className={`focus-visible:ring-accent cursor-pointer rounded-md px-2.5 py-1 text-xs transition-colors outline-none focus-visible:ring-2 disabled:opacity-50 ${
                      armed === c.id
                        ? 'bg-status-fail text-white'
                        : 'border-line text-ink-muted hover:text-ink border'
                    }`}
                  >
                    {armed === c.id ? t('chantiers.deleteSure') : t('chantiers.delete')}
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
        {error && <p className="text-status-fail text-xs">{error}</p>}
      </Band>
    </motion.div>
  )
}

export function OverviewPage({ onOpenDay }: { readonly onOpenDay: (iso: string) => void }) {
  const { t, dir, locale } = useI18n()
  const { services, health, healthError, stats } = useOps()
  const reports = useApi('reports', api.reports)

  const m = useMemo(
    () => (reports.data ? computeMetrics(reports.data.reports) : null),
    [reports.data],
  )
  const fmt = useMemo(
    () => new Intl.NumberFormat(intlLocaleOf(locale)),
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
  let state: SystemState = 'nominal'
  if (!apiUp) state = 'down'
  else if (anyDown || m.flagged > 0) state = 'degraded'

  const staleSuffix = m.dayIsStale ? ` · ${t('ribbon.stale')}` : ''
  const dayRibbonAside = m.dayISO ? `${m.dayISO}${staleSuffix}` : undefined

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

      <UnverifiedSites />

      {/* Ribbon and totals share a row: the same day, read two ways. */}
      <motion.div
        variants={rise}
        className="grid gap-x-8 gap-y-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]"
      >
        <Band title={t('ribbon.title')} aside={dayRibbonAside}>
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

        {/* The year graph answers "when", the figures under it answer "how
            much" — same column because they are read together, and a reader
            who has just spotted a busy week wants the totals without moving
            their eye back across the page. */}
        <div className="flex min-w-0 flex-col gap-5">
          <Band title={t('graph.year')} aside={fmt.format(m.total)}>
            {/* Clicking a day deep-links into the Inbox filtered to that date. */}
            <ContributionGraph rows={reports.data?.reports ?? []} onSelectDay={onOpenDay} />
          </Band>

          <Band title={t('panel.keyFigures')}>
            <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3">
              <Quantity value={fmt.format(m.week)} label={t('metric.week')} />
              <Quantity value={fmt.format(m.techniciens)} label={t('metric.techniciens')} />
              <Quantity value={fmt.format(m.flagged)} label={t('metric.flagged')} />
              <Quantity
                value={m.voiceShare === null ? '—' : `${m.voiceShare}`}
                unit={m.voiceShare === null ? undefined : '%'}
                label={t('metric.voiceShare')}
              />
              <Quantity value={fmt.format(m.undated)} label={t('metric.undatedShort')} />
              <Quantity
                value={fmt.format(m.byChantier.length)}
                label={t('weekly.chantiers')}
              />
            </div>
          </Band>
        </div>
      </motion.div>
    </motion.div>
  )
}
