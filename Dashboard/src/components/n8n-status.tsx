import { api, pickReceptionWorkflow, useApi } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { LiveDot } from '@/components/live-dot'

/**
 * Three distinct facts, never conflated:
 *   offline  - n8n does not answer, nothing is being received
 *   inactive - n8n answers but the reception workflow is switched off
 *   active   - n8n answers and the workflow is armed
 * A dashboard that showed only "up" would hide the middle case, which looks
 * healthy while silently dropping every technician's report.
 */
export function N8nStatus() {
  const { t } = useI18n()
  const { data } = useApi(api.n8n, 20_000)

  if (!data) {
    return (
      <span className="text-ink-faint flex items-center gap-2 text-xs">
        <LiveDot tone="idle" />
        {t('state.loading')}
      </span>
    )
  }

  if (!data.reachable) {
    return (
      <span className="text-status-fail flex items-center gap-2 text-xs">
        <LiveDot tone="fail" />
        {t('n8n.offline')}
      </span>
    )
  }

  if (data.authError) {
    return (
      <span className="text-status-warn flex items-center gap-2 text-xs">
        <LiveDot tone="warn" />
        {t('n8n.noKey')}
      </span>
    )
  }

  const reception = pickReceptionWorkflow(data.workflows)
  const active = reception?.active ?? false

  return (
    <span
      className={`flex items-center gap-2 text-xs ${active ? 'text-ink-muted' : 'text-status-warn'}`}
      title={reception?.name}
    >
      <LiveDot tone={active ? 'ok' : 'warn'} live={active} />
      <span className="truncate">{active ? t('n8n.active') : t('n8n.inactive')}</span>
    </span>
  )
}
