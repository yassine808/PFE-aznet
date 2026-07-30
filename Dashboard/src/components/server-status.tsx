import { api, useApi } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { LiveDot } from '@/components/live-dot'

/**
 * Whole-stack reachability, not one service.
 *
 * The browser cannot query Docker directly, so "the server is running" is
 * inferred from the two containers it can actually reach: the API and n8n.
 * Both answering is the only state reported as running; one answering is
 * reported as partial rather than green, because a half-up stack drops work.
 */
export function ServerStatus() {
  const { t } = useI18n()
  const health = useApi('health', api.health, 30_000)
  const n8n = useApi('n8n', api.n8n, 30_000)

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

  const up = apiUp && n8nUp
  const partial = apiUp !== n8nUp

  return (
    <span
      className={`flex items-center gap-2 text-xs ${up ? 'text-ink-muted' : partial ? 'text-status-warn' : 'text-status-fail'}`}
      title={`API ${apiUp ? 'up' : 'down'} · n8n ${n8nUp ? 'up' : 'down'}`}
    >
      <LiveDot tone={up ? 'ok' : partial ? 'warn' : 'fail'} live={up} />
      <span className="truncate">
        {up ? t('server.running') : partial ? t('server.partial') : t('server.stopped')}
      </span>
    </span>
  )
}
