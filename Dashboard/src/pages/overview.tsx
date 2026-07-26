import { useMemo } from 'react'
import { motion } from 'motion/react'
import { api, useApi } from '@/lib/api'
import { computeMetrics, formatUptime, isFlagged, num } from '@/lib/metrics'
import { useI18n } from '@/lib/i18n'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { LiveDot } from '@/components/live-dot'
import { cn } from '@/lib/utils'

const rise = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 100, damping: 20 } },
}

/** Headline figures sit on the page itself, not in boxes. Boxes would compete with them. */
function Figure({ value, label, tone }: { value: string; label: string; tone?: 'flag' }) {
  return (
    <div className="flex flex-col gap-1">
      <span className={cn('tabular text-3xl leading-none font-medium', tone === 'flag' ? 'text-status-warn' : 'text-ink')}>
        {value}
      </span>
      <span className="text-ink-faint text-xs">{label}</span>
    </div>
  )
}

function Panel({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn('border-line bg-surface edge rounded-xl border p-6', className)}>
      <h2 className="text-ink-faint mb-5 text-[0.6875rem] font-medium tracking-wide uppercase">{title}</h2>
      {children}
    </section>
  )
}

export function OverviewPage() {
  const { t, locale } = useI18n()
  const reports = useApi(api.reports, 60_000)
  const health = useApi(api.health, 30_000)

  const m = useMemo(() => (reports.data ? computeMetrics(reports.data.reports) : null), [reports.data])
  const fmt = useMemo(() => new Intl.NumberFormat(locale === 'ar' ? 'ar-MA' : locale === 'en' ? 'en-GB' : 'fr-FR'), [locale])

  if (reports.error) return <ErrorState message={reports.error} onRetry={reports.reload} />

  if (reports.loading || !m) {
    return (
      <div className="flex flex-col gap-8 pt-8">
        <div className="flex gap-12">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="flex flex-col gap-2">
              <Skeleton className="h-8 w-16" />
              <Skeleton className="h-3 w-24" />
            </div>
          ))}
        </div>
        <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
          <Skeleton className="h-64 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      </div>
    )
  }

  if (m.total === 0) return <EmptyState />

  const maxChantier = Math.max(...m.byChantier.map((c) => c.count), 1)
  const apiUp = !health.error && health.data?.status === 'ok'

  return (
    <motion.div
      variants={{ show: { transition: { staggerChildren: 0.05 } } }}
      initial="hidden"
      animate="show"
      className="flex flex-col gap-8 pt-8"
    >
      {/* Headline row */}
      <motion.div variants={rise} className="flex flex-wrap gap-x-12 gap-y-6">
        <Figure value={fmt.format(m.today)} label={t('metric.today')} />
        <Figure value={fmt.format(m.week)} label={t('metric.week')} />
        <Figure value={fmt.format(m.total)} label={t('metric.total')} />
        <Figure value={fmt.format(m.techniciens)} label={t('metric.techniciens')} />
        <Figure value={fmt.format(m.flagged)} label={t('metric.flagged')} tone={m.flagged ? 'flag' : undefined} />
      </motion.div>

      {m.undated > 0 && (
        <motion.p variants={rise} className="text-status-warn text-xs">
          {t('metric.undated')}: <span className="tabular">{fmt.format(m.undated)}</span>
        </motion.p>
      )}

      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        {/* Production today + per-chantier distribution */}
        <motion.div variants={rise} className="flex flex-col gap-5">
          <Panel title={t('panel.productionToday')}>
            <div className="divide-line grid grid-cols-2 divide-y sm:grid-cols-4 sm:divide-x sm:divide-y-0">
              {[
                { v: m.totalsToday.goulottes_m, l: t('metric.goulottes'), u: 'm' },
                { v: m.totalsToday.cables_m, l: t('metric.cables'), u: 'm' },
                { v: m.totalsToday.bureaux, l: t('metric.bureaux'), u: '' },
                { v: m.totalsToday.panneaux, l: t('metric.panneaux'), u: '' },
              ].map((x, i) => (
                <div key={x.l} className={cn('py-3', i > 0 && 'sm:ps-5')}>
                  <p className="tabular text-ink text-xl leading-none font-medium">
                    {fmt.format(x.v)}
                    {x.u && <span className="text-ink-faint ms-1 text-xs">{x.u}</span>}
                  </p>
                  <p className="text-ink-faint mt-1.5 text-xs">{x.l}</p>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title={t('panel.byChantier')}>
            {m.byChantier.length === 0 ? (
              <EmptyState />
            ) : (
              <ul className="flex flex-col gap-3">
                {m.byChantier.map((c) => (
                  <li key={c.name} className="flex items-center gap-4">
                    <span className="text-ink w-40 shrink-0 truncate text-sm">{c.name}</span>
                    <span className="bg-line h-1.5 min-w-0 flex-1 overflow-hidden rounded-full">
                      <motion.span
                        className="bg-accent block h-full rounded-full"
                        initial={{ scaleX: 0 }}
                        animate={{ scaleX: c.count / maxChantier }}
                        style={{ transformOrigin: 'left' }}
                        transition={{ type: 'spring', stiffness: 100, damping: 20 }}
                      />
                    </span>
                    <span className="tabular text-ink-muted w-8 shrink-0 text-end text-sm">{fmt.format(c.count)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </motion.div>

        {/* Ops column */}
        <motion.div variants={rise} className="flex flex-col gap-5">
          <Panel title={t('panel.system')}>
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between gap-3">
                <span className="text-ink-muted flex items-center gap-2 text-sm">
                  <LiveDot tone={apiUp ? 'ok' : 'fail'} live={apiUp} />
                  {apiUp ? t('status.live') : t('status.unreachable')}
                </span>
                {health.data && <span className="tabular text-ink-faint text-xs">v{health.data.version}</span>}
              </div>

              {health.data && (
                <dl className="divide-line flex flex-col divide-y text-sm">
                  <div className="flex items-baseline justify-between gap-3 py-2">
                    <dt className="text-ink-faint text-xs">{t('metric.uptime')}</dt>
                    <dd className="tabular text-ink">{formatUptime(health.data.uptime_seconds)}</dd>
                  </div>
                  <div className="flex items-baseline justify-between gap-3 py-2">
                    <dt className="text-ink-faint text-xs">{t('metric.stt')}</dt>
                    <dd className="tabular text-ink">{health.data.stt_default}</dd>
                  </div>
                  {m.voiceShare !== null && (
                    <div className="flex items-baseline justify-between gap-3 py-2">
                      <dt className="text-ink-faint text-xs">{t('metric.voiceShare')}</dt>
                      <dd className="tabular text-ink">{m.voiceShare}%</dd>
                    </div>
                  )}
                </dl>
              )}

              {health.error && <ErrorState message={health.error} onRetry={health.reload} />}
            </div>
          </Panel>

          <Panel title={t('panel.recent')}>
            {m.recent.length === 0 ? (
              <EmptyState />
            ) : (
              <ul className="divide-line flex flex-col divide-y">
                {m.recent.map((r) => (
                  <li key={r._row} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
                    <LiveDot tone={isFlagged(r.flag_review) ? 'warn' : 'ok'} />
                    <div className="min-w-0 flex-1">
                      <p className="text-ink truncate text-sm">{r.technicien || '—'}</p>
                      <p className="text-ink-faint truncate text-xs">{r.chantier || '—'}</p>
                    </div>
                    <span className="tabular text-ink-muted shrink-0 text-xs">
                      {num(r.goulottes_m) ? `${fmt.format(num(r.goulottes_m))} m` : (r.heure ?? '')}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </motion.div>
      </div>
    </motion.div>
  )
}
