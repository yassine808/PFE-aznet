import { useState } from 'react'
import { motion } from 'motion/react'
import { ArrowClockwiseIcon, XIcon } from '@phosphor-icons/react'
import { api, dismissQueueItem, runJob, useApi } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

/**
 * The Sheet retry queue: reports Google refused, parked in `failed_writes`
 * (see CLAUDE.md's reply-first ordering). The 5-minute cron already drains
 * this — this page exists so a human can see what's stuck and force a pass
 * without waiting, or drop a dead letter that will never succeed.
 */
export function QueuePage() {
  const list = useApi('sheet-queue', api.queue)
  const { t, locale } = useI18n()
  const { settings } = useSettings()
  const [busy, setBusy] = useState<number | 'job' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const pending = list.data?.pending ?? []
  // Google refusing on quota is not the same as a stuck queue: the drain is
  // waiting for the window and spends no attempt meanwhile. Saying so is the
  // difference between "nothing is happening" and "nothing should be".
  const pausedUntil = list.data?.paused_until ?? null
  const paused = pausedUntil !== null && pausedUntil * 1000 > Date.now()

  const runNow = async () => {
    setBusy('job')
    setError(null)
    try {
      await runJob('sheet_queue')
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

  const dismiss = async (id: number) => {
    setBusy(id)
    setError(null)
    try {
      await dismissQueueItem(id)
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-6 pt-8"
    >
      <div className="flex flex-wrap items-center gap-4">
        <p className="text-ink-faint max-w-[65ch] text-sm">{t('queue.intro')}</p>
        <button
          type="button"
          onClick={runNow}
          disabled={busy !== null}
          className={cn(
            'border-line text-ink-muted hover:text-ink focus-visible:ring-accent ms-auto flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2',
            busy !== null && 'cursor-not-allowed opacity-50',
          )}
        >
          <ArrowClockwiseIcon size={13} weight="bold" className={busy === 'job' ? 'animate-spin' : ''} />
          {t('queue.runNow')}
        </button>
      </div>

      {paused && (
        <p className="border-status-warn/40 text-status-warn rounded-md border border-dashed px-3 py-2 text-xs">
          {t('queue.paused')}{' '}
          {new Date((pausedUntil as number) * 1000).toLocaleTimeString(locale, {
            hour12: settings.timeFormat === '12h',
          })}
        </p>
      )}

      {error && <p className="text-status-fail text-xs break-all">{error}</p>}

      {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
      {list.loading && !list.data && <Skeleton className="h-64" />}
      {list.data && pending.length === 0 && <EmptyState body={t('queue.empty')} />}

      {pending.length > 0 && (
        <ul className="flex flex-col gap-3">
          {pending.map((item) => (
            <li
              key={item.id}
              className="border-line bg-surface edge flex flex-col gap-2 rounded-xl border p-4"
            >
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-ink-faint tabular text-xs">
                  {item.created_at
                    ? new Date(item.created_at).toLocaleString(locale, {
                        dateStyle: 'medium',
                        timeStyle: 'short',
                        hour12: settings.timeFormat === '12h',
                      })
                    : '—'}
                </span>
                {item.status && (
                  <span
                    className={cn(
                      'rounded-full border px-2 py-0.5 text-[0.625rem]',
                      item.status === 'abandoned'
                        ? 'border-status-fail/40 text-status-fail'
                        : item.status === 'retrying'
                          ? 'border-status-warn/40 text-status-warn'
                          : 'border-line text-ink-faint',
                    )}
                  >
                    {t(`queue.status.${item.status}`)}
                  </span>
                )}
                {typeof item.attempts === 'number' && (
                  <span className="border-line text-ink-faint rounded-full border px-2 py-0.5 text-[0.625rem] tabular">
                    {item.attempts} {t('queue.attempts')}
                  </span>
                )}
                {item.correlation_id && (
                  <span className="text-ink-faint truncate text-[0.625rem]">
                    {t('queue.correlationId')}: {item.correlation_id}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => dismiss(item.id)}
                  disabled={busy !== null}
                  aria-label={t('queue.dismiss')}
                  className="text-ink-faint hover:text-status-fail focus-visible:ring-accent ms-auto cursor-pointer rounded p-1 transition-colors outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <XIcon size={14} />
                </button>
              </div>

              <p className="text-status-fail text-xs break-words">
                {t('queue.error')}: {item.last_error}
              </p>

              <pre className="text-ink-faint bg-canvas edge overflow-x-auto rounded-md border border-dashed p-2 text-[0.6875rem]">
                {JSON.stringify(item.payload, null, 2)}
              </pre>
            </li>
          ))}
        </ul>
      )}
    </motion.div>
  )
}
