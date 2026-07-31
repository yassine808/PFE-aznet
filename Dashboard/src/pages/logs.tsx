import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { CheckCircleIcon, WarningCircleIcon, XCircleIcon } from '@phosphor-icons/react'
import { api, useApi } from '@/lib/api'
import type { Async, LogEntry, LogStats } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { ChannelIcon } from '@/components/channel-icon'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

/**
 * Live pipeline timeline. n8n writes one row per stage and the API writes its
 * own errors under the same correlation_id, so a message's whole journey —
 * across two processes — reads top to bottom here.
 *
 * Shares the 'logs' cache key with OpsProvider, which already polls it above the
 * router. That means this page paints instantly on arrival instead of flashing a
 * skeleton, and adds no extra request.
 */

type Filter = 'all' | 'error' | 'info'

const LEVEL = {
  error: { Icon: XCircleIcon, dot: 'bg-status-fail', text: 'text-status-fail' },
  warn: { Icon: WarningCircleIcon, dot: 'bg-status-warn', text: 'text-status-warn' },
  info: { Icon: CheckCircleIcon, dot: 'bg-status-ok', text: 'text-status-ok' },
} as const

function levelOf(entry: LogEntry) {
  return LEVEL[entry.level as keyof typeof LEVEL] ?? LEVEL.info
}

function LogsList({
  logs,
  entries,
  shown,
  locale,
  emptyBody,
}: {
  readonly logs: Async<{ logs: LogEntry[]; stats: LogStats }>
  readonly entries: LogEntry[]
  readonly shown: LogEntry[]
  readonly locale: string
  readonly emptyBody: string
}) {
  if (logs.error) return <ErrorState message={logs.error} onRetry={logs.reload} />
  if (logs.loading && entries.length === 0) return <Skeleton className="h-64" />
  if (shown.length === 0) return <EmptyState body={emptyBody} />
  return (
    <ul className="flex flex-col">
      {shown.map((entry) => {
        const level = levelOf(entry)
        return (
          <li
            key={entry.id}
            className="border-line hover:bg-surface flex items-start gap-3 border-b py-2.5 transition-colors last:border-b-0"
          >
            <level.Icon size={15} className={cn('mt-0.5 shrink-0', level.text)} weight="fill" />

            <span className="text-ink-faint tabular w-16 shrink-0 text-xs">
              {new Date(entry.ts).toLocaleTimeString(locale, {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              })}
            </span>

            <span className="text-ink-muted w-24 shrink-0 truncate text-xs">{entry.stage}</span>

            <span className={cn('min-w-0 flex-1 text-xs break-words', level.text)}>
              {entry.message || '—'}
            </span>

            {entry.technicien && (
              <span className="text-ink-faint hidden shrink-0 items-center gap-1.5 text-xs sm:flex">
                {entry.channel && (
                  <ChannelIcon channel={entry.channel as 'telegram' | 'whatsapp'} size={12} />
                )}
                {entry.technicien}
              </span>
            )}

            {typeof entry.duration_ms === 'number' && (
              <span className="text-ink-faint tabular w-14 shrink-0 text-end text-xs">
                {entry.duration_ms}ms
              </span>
            )}
          </li>
        )
      })}
    </ul>
  )
}

export function LogsPage() {
  const { t, locale } = useI18n()
  const { settings } = useSettings()
  const logs = useApi('logs', api.logs, settings.refreshMs || undefined)
  const [filter, setFilter] = useState<Filter>('all')

  const entries = logs.data?.logs ?? []
  const shown = useMemo(() => {
    if (filter === 'all') return entries
    // "info" means "not an error" — a warning is a success with a caveat, and
    // hiding it under the errors tab would overstate how often things break.
    if (filter === 'error') return entries.filter((e) => e.level === 'error')
    return entries.filter((e) => e.level !== 'error')
  }, [entries, filter])

  const errorCount = entries.filter((e) => e.level === 'error').length

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-6 pt-8"
    >
      <div className="flex flex-wrap items-center gap-4">
        <p className="text-ink-faint max-w-[60ch] text-sm">{t('logs.intro')}</p>

        <fieldset className="border-line m-0 ms-auto flex rounded-md border p-0.5">
          <legend className="sr-only">{t('logs.filter')}</legend>
          {(['all', 'info', 'error'] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              aria-pressed={filter === f}
              className={cn(
                'rounded px-2.5 py-1 text-xs transition-colors',
                filter === f
                  ? 'bg-slate-100 text-ink dark:bg-slate-850'
                  : 'text-ink-faint hover:text-ink',
              )}
            >
              {t(`logs.filter.${f}`)}
              {f === 'error' && errorCount > 0 && (
                <span className="text-status-fail ms-1.5 tabular">{errorCount}</span>
              )}
            </button>
          ))}
        </fieldset>
      </div>

      <LogsList logs={logs} entries={entries} shown={shown} locale={locale} emptyBody={t('logs.empty')} />

      <p className="text-ink-faint text-xs">
        {t('logs.retention')} {logs.data?.stats.retention_days ?? 30} {t('logs.days')}
      </p>
    </motion.div>
  )
}
