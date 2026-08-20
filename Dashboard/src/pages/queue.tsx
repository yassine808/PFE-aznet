import { useState } from 'react'
import { motion } from 'motion/react'
import { ArrowClockwiseIcon, XIcon } from '@phosphor-icons/react'
import { api, dismissQueueItem, runJob, useApi } from '@/lib/api'
import type { QueuedMessage } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

/**
 * Both retry queues, in pipeline order.
 *
 * `message_queue` first: messages that never became a report because STT or
 * extraction failed. Then `failed_writes`: finished reports Google refused (see
 * CLAUDE.md's reply-first ordering). They are separate tables on purpose — one
 * holds an audio blob, the other a parsed report — but one page, because an
 * operator asking "where is that report?" does not know which stage lost it.
 *
 * The crons already drain both. This page exists so a human can see what is
 * stuck, force a pass without waiting, and drop a dead letter that will never
 * succeed.
 */
/** Border and text colour of a status pill. Only the two bad states are coloured. */
function statusTone(status: string): string {
  if (status === 'abandoned') return 'border-status-fail/40 text-status-fail'
  if (status === 'retrying') return 'border-status-warn/40 text-status-warn'
  return 'border-line text-ink-faint'
}

export function QueuePage() {
  const list = useApi('sheet-queue', api.queue)
  const msgs = useApi('message-queue', api.messageQueue)
  const { t, locale } = useI18n()
  const { settings } = useSettings()
  const [busy, setBusy] = useState<number | 'job' | 'msgjob' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const pending = list.data?.pending ?? []
  // Google refusing on quota is not the same as a stuck queue: the drain is
  // waiting for the window and spends no attempt meanwhile. Saying so is the
  // difference between "nothing is happening" and "nothing should be".
  const pausedUntil = list.data?.paused_until ?? null
  const paused = pausedUntil !== null && pausedUntil * 1000 > Date.now()

  const queuedMessages = msgs.data?.pending ?? []
  // A different quota from the Sheet one above: this is the extraction chain
  // (Groq + both Gemini models) refusing, which stops the retry loop calling
  // the model at all. Reception keeps running either way.
  const msgPausedUntil = msgs.data?.paused_until ?? null
  const msgPaused = msgPausedUntil !== null && msgPausedUntil * 1000 > Date.now()

  const runMessagesNow = async () => {
    setBusy('msgjob')
    setError(null)
    try {
      await runJob('message_queue')
      msgs.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

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
      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="max-w-[65ch]">
            <h2 className="text-ink text-sm font-medium">{t('queue.messages.title')}</h2>
            <p className="text-ink-faint mt-1 text-sm">{t('queue.messages.intro')}</p>
          </div>
          <button
            type="button"
            onClick={runMessagesNow}
            disabled={busy !== null}
            className={cn(
              'border-line text-ink-muted hover:text-ink focus-visible:ring-accent ms-auto flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2',
              busy !== null && 'cursor-not-allowed opacity-50',
            )}
          >
            <ArrowClockwiseIcon
              size={13}
              weight="bold"
              className={busy === 'msgjob' ? 'animate-spin' : ''}
            />
            {t('queue.messages.runNow')}
          </button>
        </div>

        {msgPaused && (
          <p className="border-status-warn/40 text-status-warn rounded-md border border-dashed px-3 py-2 text-xs">
            {t('queue.messages.paused')}{' '}
            {new Date((msgPausedUntil as number) * 1000).toLocaleTimeString(locale, {
              hour12: settings.timeFormat === '12h',
            })}
          </p>
        )}

        {msgs.error && <ErrorState message={msgs.error} onRetry={msgs.reload} />}
        {msgs.loading && !msgs.data && <Skeleton className="h-32" />}
        {msgs.data && queuedMessages.length === 0 && (
          <EmptyState body={t('queue.messages.empty')} />
        )}

        {queuedMessages.length > 0 && (
          <ul className="flex flex-col gap-3">
            {queuedMessages.map((m: QueuedMessage) => (
              <li
                key={m.id}
                className="border-line bg-surface edge flex flex-col gap-2 rounded-xl border p-4"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <span className="text-ink-faint tabular text-xs">
                    {/* When the technician SENT it. The received time is not the
                        same fact and is what put reports on the wrong day before. */}
                    {m.sent_date ? `${m.sent_date} ${m.sent_heure ?? ''}`.trim() : '—'}
                  </span>
                  {m.technicien && <span className="text-ink text-xs">{m.technicien}</span>}
                  <span className="border-line text-ink-faint rounded-full border px-2 py-0.5 text-[0.625rem]">
                    {t(`queue.messages.kind.${m.kind}`)}
                  </span>
                  <span
                    className={cn(
                      'rounded-full border px-2 py-0.5 text-[0.625rem]',
                      statusTone(m.status),
                    )}
                  >
                    {t(`queue.status.${m.status}`)}
                  </span>
                  <span className="border-line text-ink-faint tabular rounded-full border px-2 py-0.5 text-[0.625rem]">
                    {m.attempts}
                    {msgs.data?.max_attempts ? `/${msgs.data.max_attempts}` : ''}{' '}
                    {t('queue.attempts')}
                  </span>
                  {m.status !== 'abandoned' && m.next_try_at && (
                    <span className="text-ink-faint text-[0.625rem]">
                      {t('queue.messages.nextTry')}{' '}
                      {new Date(m.next_try_at).toLocaleTimeString(locale, {
                        hour12: settings.timeFormat === '12h',
                      })}
                    </span>
                  )}
                </div>
                {m.last_error && (
                  <p className="text-status-fail text-xs break-all">{m.last_error}</p>
                )}
                {m.correlation_id && (
                  <span className="text-ink-faint truncate text-[0.625rem]">
                    {t('queue.correlationId')}: {m.correlation_id}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <h2 className="text-ink border-line border-t pt-6 text-sm font-medium">
        {t('queue.sheet.title')}
      </h2>

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
          <ArrowClockwiseIcon
            size={13}
            weight="bold"
            className={busy === 'job' ? 'animate-spin' : ''}
          />
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
                      statusTone(item.status),
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
