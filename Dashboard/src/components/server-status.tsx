import { api, useApi } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { LiveDot } from '@/components/live-dot'

type ServerStatusLevel = 'up' | 'partial' | 'down'

function levelOf(up: boolean, partial: boolean): ServerStatusLevel {
  if (up) return 'up'
  return partial ? 'partial' : 'down'
}

/**
 * Whole-stack reachability, not one service.
 *
 * The browser cannot query Docker directly, so "the server is running" is
 * inferred from the two containers it can actually reach: the API and n8n.
 * Both answering is the only state reported as running; one answering is
 * reported as partial rather than green, because a half-up stack drops work.
 */
export function ServerStatus() {
  const { t, locale } = useI18n()
  const health = useApi('health', api.health, 30_000)
  const n8n = useApi('n8n', api.n8n, 30_000)
  // Reachable is not listening. Polling and the webhook can be dead while every
  // container answers — 2026-08-19, an hour of silence under a green dot.
  const listening = useApi('n8n-listening', api.n8nListening, 30_000)

  const apiUp = !health.error && health.data?.status === 'ok'
  const n8nUp = n8n.data?.reachable ?? false
  const settled = health.data !== null || health.error !== null

  if (!settled) {
    return (
      <span className="text-ink-faint flex items-center gap-2 text-xs">
        <LiveDot tone="idle" />
        {t('state.loading')}
      </span>
    )
  }

  const stale = listening.data?.stale === true
  const up = apiUp && n8nUp && !stale
  const partial = apiUp !== n8nUp || (apiUp && n8nUp && stale)
  const level = levelOf(up, partial)
  const textClass = { up: 'text-ink-muted', partial: 'text-status-warn', down: 'text-status-fail' }[
    level
  ]
  const tone = { up: 'ok', partial: 'warn', down: 'fail' }[level] as 'ok' | 'warn' | 'fail'
  const label = stale && apiUp && n8nUp
    ? t('server.stale')
    : { up: t('server.running'), partial: t('server.partial'), down: t('server.stopped') }[level]

  return (
    <span
      className={`flex items-center gap-2 text-xs ${textClass}`}
      title={`API ${apiUp ? 'up' : 'down'} · n8n ${n8nUp ? 'up' : 'down'}${
        listening.data?.last_execution_at
          ? ` · ${t('server.lastExecution')}: ${new Date(listening.data.last_execution_at).toLocaleString(locale)}`
          : ''
      }`}
    >
      <LiveDot tone={tone} live={up} />
      <span className="truncate">{label}</span>
    </span>
  )
}
