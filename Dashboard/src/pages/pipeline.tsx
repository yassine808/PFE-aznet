import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { CaretRightIcon, MagnifyingGlassIcon } from '@phosphor-icons/react'
import { api, useApi } from '@/lib/api'
import { buildFunnel, buildTraces, latency, STAGES, type Trace } from '@/lib/pipeline'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { ChannelIcon } from '@/components/channel-icon'
import { LiveDot } from '@/components/live-dot'
import { cn } from '@/lib/utils'

const LEVEL_TONE: Record<string, 'ok' | 'warn' | 'fail'> = {
  info: 'ok',
  warn: 'warn',
  error: 'fail',
}

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

/** One row per message, expandable into its full cross-process timeline. */
function TraceRow({ trace, pad }: { trace: Trace; pad: string }) {
  const { t, locale } = useI18n()
  const [open, setOpen] = useState(false)

  const time = new Intl.DateTimeFormat(locale === 'ar' ? 'ar-MA' : locale === 'en' ? 'en-GB' : 'fr-FR', {
    dateStyle: 'short',
    timeStyle: 'medium',
  })

  return (
    <li className="border-line border-b last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={cn('hover:bg-surface flex w-full items-center gap-3 text-start transition-colors', pad)}
      >
        <CaretRightIcon
          size={12}
          className={cn('text-ink-faint shrink-0 transition-transform rtl:rotate-180', open && 'rotate-90')}
        />
        {trace.channel && <ChannelIcon channel={trace.channel} size={13} className="text-ink-muted" />}
        <span className="text-ink w-28 shrink-0 truncate text-sm">{trace.technicien || '—'}</span>

        {/* Stage dots: a missing stage is a gap, not an absence of information. */}
        <span className="flex shrink-0 items-center gap-1.5">
          {STAGES.map((s) => {
            const level = trace.reached.get(s)
            return (
              <span key={s} title={`${t(`stage.${s}`)}${level ? ` · ${level}` : ' · —'}`}>
                {level ? (
                  <LiveDot tone={LEVEL_TONE[level] ?? 'ok'} />
                ) : (
                  <span className="border-line block size-2 rounded-full border" />
                )}
              </span>
            )
          })}
        </span>

        <span className="tabular text-ink-faint ms-auto shrink-0 text-xs">
          {trace.totalMs !== null ? `${(trace.totalMs / 1000).toFixed(1)}s` : '—'}
        </span>
        <span className="tabular text-ink-faint hidden shrink-0 text-xs sm:block">
          {trace.startedAt ? time.format(trace.startedAt) : '—'}
        </span>
      </button>

      {open && (
        <div className="bg-surface/60 px-4 py-3">
          <p className="tabular text-ink-faint mb-2 text-[0.6875rem] break-all">{trace.correlationId}</p>
          <ol className="divide-line flex flex-col divide-y">
            {trace.events.map((e) => (
              <li key={e.id} className="flex items-baseline gap-3 py-1.5 text-xs">
                <LiveDot tone={LEVEL_TONE[e.level] ?? 'ok'} />
                <span className="tabular text-ink-faint w-24 shrink-0">
                  {Number.isFinite(Date.parse(e.ts)) ? time.format(Date.parse(e.ts)) : '—'}
                </span>
                <span className="text-ink w-28 shrink-0">{t(`stage.${e.stage}`)}</span>
                <span className={cn('min-w-0 flex-1', e.level === 'error' ? 'text-status-fail' : 'text-ink-muted')}>
                  {e.message || '—'}
                </span>
                {typeof e.duration_ms === 'number' && e.duration_ms > 0 && (
                  <span className="tabular text-ink-faint shrink-0">{(e.duration_ms / 1000).toFixed(1)}s</span>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </li>
  )
}

export function PipelinePage() {
  const { t, locale } = useI18n()
  const { settings } = useSettings()
  const logs = useApi('logs', api.logs, settings.refreshMs || undefined)

  const [level, setLevel] = useState('')
  const [channel, setChannel] = useState('')
  const [query, setQuery] = useState('')

  const fmt = useMemo(
    () => new Intl.NumberFormat(locale === 'ar' ? 'ar-MA' : locale === 'en' ? 'en-GB' : 'fr-FR'),
    [locale],
  )

  const entries = logs.data?.logs ?? []
  const allTraces = useMemo(() => buildTraces(entries), [entries])
  const funnel = useMemo(() => buildFunnel(allTraces), [allTraces])

  const channels = useMemo(
    () => [...new Set(entries.map((l) => (l.channel ?? '').trim()).filter(Boolean))],
    [entries],
  )

  const traces = useMemo(() => {
    const q = query.trim().toLowerCase()
    return allTraces
      .filter((tr) => (level === 'error' ? tr.hasError : level === 'warn' ? tr.events.some((e) => e.level === 'warn') : true))
      .filter((tr) => (channel ? tr.channel === channel : true))
      .filter((tr) =>
        q
          ? tr.correlationId.toLowerCase().includes(q) ||
            (tr.technicien ?? '').toLowerCase().includes(q) ||
            tr.events.some((e) => (e.message ?? '').toLowerCase().includes(q))
          : true,
      )
  }, [allTraces, level, channel, query])

  const sttLatency = useMemo(() => latency(entries, 'transcribed'), [entries])
  const extractLatency = useMemo(() => latency(entries, 'extracted'), [entries])

  if (logs.error) return <ErrorState message={logs.error} onRetry={logs.reload} />
  if (logs.loading) {
    return (
      <div className="flex flex-col gap-4 pt-8">
        <Skeleton className="h-28" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  const maxFunnel = Math.max(...funnel.map((f) => f.count), 1)
  const pad = settings.density === 'compact' ? 'px-2 py-1.5' : 'px-2 py-2.5'

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-8 pt-8"
    >
      <p className="text-ink-faint max-w-[70ch] text-sm">{t('pipeline.intro')}</p>

      <div className="grid gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        {/* Funnel: where messages stop. */}
        <Band title={t('pipeline.funnel')} aside={`${fmt.format(allTraces.length)} ${t('pipeline.traces')}`}>
          {allTraces.length === 0 ? (
            <EmptyState body={t('pipeline.noTraces')} />
          ) : (
            <ul className="flex flex-col gap-2.5">
              {funnel.map((step) => (
                <li key={step.stage} className="flex items-center gap-3">
                  <span className="text-ink w-32 shrink-0 text-sm">{t(`stage.${step.stage}`)}</span>
                  <span className="bg-line h-2 min-w-0 flex-1 overflow-hidden rounded-full">
                    <motion.span
                      className={cn('block h-full rounded-full', step.errors > 0 ? 'bg-status-warn' : 'bg-accent')}
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: step.count / maxFunnel }}
                      style={{ transformOrigin: 'left' }}
                      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
                    />
                  </span>
                  <span className="tabular text-ink w-8 shrink-0 text-end text-sm">{fmt.format(step.count)}</span>
                  {/* Drop-off is the number that matters: it is messages that died here. */}
                  <span className="tabular text-status-fail w-14 shrink-0 text-end text-xs">
                    {step.dropped > 0 ? `−${fmt.format(step.dropped)}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Band>

        <Band title={t('pipeline.latency')}>
          <div className="flex flex-col gap-4">
            {[
              [t('stage.transcribed'), sttLatency],
              [t('stage.extracted'), extractLatency],
            ].map(([label, l]) => (
              <div key={String(label)} className="flex flex-col gap-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-ink text-sm">{String(label)}</span>
                  <span className="tabular text-ink-faint text-xs">
                    {l ? `${fmt.format((l as { n: number }).n)} ${t('pipeline.samples')}` : '—'}
                  </span>
                </div>
                {l ? (
                  <div className="text-ink-muted flex gap-5 text-xs">
                    <span>
                      {t('pipeline.median')}{' '}
                      <span className="tabular text-ink">
                        {((l as { median: number }).median / 1000).toFixed(1)}s
                      </span>
                    </span>
                    <span>
                      p95{' '}
                      <span className="tabular text-ink">{((l as { p95: number }).p95 / 1000).toFixed(1)}s</span>
                    </span>
                  </div>
                ) : (
                  <span className="text-ink-faint text-xs">{t('pipeline.noTiming')}</span>
                )}
              </div>
            ))}

            <div className="border-line flex items-baseline justify-between gap-3 border-t pt-3">
              <span className="text-ink-faint text-xs">{t('metric.errors24h')}</span>
              <span className="tabular text-ink text-sm">{fmt.format(logs.data?.stats.last_24h.error ?? 0)}</span>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-ink-faint text-xs">{t('metric.pendingWrites')}</span>
              <span className="tabular text-ink text-sm">{fmt.format(logs.data?.stats.pending_sheet_writes ?? 0)}</span>
            </div>
          </div>
        </Band>
      </div>

      <Band title={t('pipeline.traces')} aside={fmt.format(traces.length)}>
        {/* Filters in one row above the list. */}
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <div className="border-line focus-within:border-accent flex min-w-56 flex-1 items-center gap-2 rounded-md border px-3 py-2 transition-colors">
            <MagnifyingGlassIcon size={14} className="text-ink-faint shrink-0" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('pipeline.search')}
              aria-label={t('pipeline.search')}
              className="text-ink placeholder:text-ink-faint min-w-0 flex-1 bg-transparent text-sm outline-none"
            />
          </div>

          <Segmented
            value={level}
            onChange={setLevel}
            options={[
              { v: '', label: t('inbox.all') },
              { v: 'warn', label: t('status.warn') },
              { v: 'error', label: t('status.failed') },
            ]}
            label={t('pipeline.level')}
          />

          {channels.length > 1 && (
            <Segmented
              value={channel}
              onChange={setChannel}
              options={[{ v: '', label: t('inbox.all') }, ...channels.map((c) => ({ v: c, label: c }))]}
              label={t('inbox.channel')}
            />
          )}
        </div>

        {traces.length === 0 ? (
          <EmptyState body={allTraces.length === 0 ? t('pipeline.noTraces') : t('reports.noMatch')} />
        ) : (
          <ul className="border-line rounded-lg border">
            {traces.map((tr) => (
              <TraceRow key={tr.correlationId} trace={tr} pad={pad} />
            ))}
          </ul>
        )}
      </Band>
    </motion.div>
  )
}

function Segmented({
  value,
  onChange,
  options,
  label,
}: {
  value: string
  onChange: (v: string) => void
  options: { v: string; label: string }[]
  label: string
}) {
  return (
    <div className="border-line flex rounded-md border p-0.5" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.v}
          type="button"
          onClick={() => onChange(o.v)}
          aria-pressed={o.v === value}
          className={cn(
            'rounded px-2.5 py-1 text-xs capitalize transition-colors',
            o.v === value ? 'bg-slate-100 text-ink dark:bg-slate-850' : 'text-ink-faint hover:text-ink',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
