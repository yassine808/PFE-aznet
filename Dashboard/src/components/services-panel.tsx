import { api, useApi } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { LiveDot } from '@/components/live-dot'
import { ServiceIcon } from '@/components/channel-icon'
import { availability, timeline } from '@/lib/uptime'
import type { ServiceRow, ServiceState } from '@/lib/services'

const SLOT_CLASS: Record<ServiceState, string> = {
  ok: 'bg-status-ok',
  warn: 'bg-status-warn',
  fail: 'bg-status-fail',
  idle: 'bg-ink-faint/35',
}

/**
 * Status strip: one column per minute for the last hour, read from Postgres.
 *
 * Columns carry a 1px gap so adjacent same-state minutes stay countable rather
 * than merging into one bar. Unrecorded minutes render as an empty track.
 */
function UptimeStrip({ slots, pct }: { slots: (ServiceState | null)[]; pct: number | null }) {
  const { t } = useI18n()
  return (
    <div className="flex items-center gap-3">
      <div
        className="flex h-4 flex-1 items-stretch gap-px"
        role="img"
        aria-label={t('uptime.lastHour')}
      >
        {slots.map((s, i) => (
          <span
            key={i}
            className={`flex-1 rounded-[1px] ${s ? SLOT_CLASS[s] : 'bg-line/60'}`}
            title={s ? t(`svc.state.${s}`) : t('uptime.noRecord')}
          />
        ))}
      </div>
      <span className="tabular text-ink-faint w-9 shrink-0 text-end text-xs">
        {pct === null ? '—' : `${pct}%`}
      </span>
    </div>
  )
}

export function ServicesPanel({ rows }: { rows: ServiceRow[] }) {
  const { t } = useI18n()
  // History comes from Postgres now, so it covers time the dashboard was closed.
  const samples = useApi('service-samples', api.samples, 60_000)

  return (
    <ul className="divide-line flex flex-col divide-y">
      {rows.map((r) => {
        const slots = timeline(samples.data?.samples ?? [], r.key)
        return (
          <li key={r.key} className="flex flex-col gap-1.5 py-2 first:pt-0 last:pb-0">
            <div className="flex items-baseline gap-2.5">
              <span className="translate-y-[3px]">
                <LiveDot tone={r.state} live={r.state === 'ok'} />
              </span>
              <ServiceIcon service={r.key} className="text-ink-muted translate-y-[2px]" size={13} />
              <span className="text-ink min-w-0 flex-1 truncate text-sm">{t(r.labelKey)}</span>
              <span
                className={`text-xs ${r.state === 'fail' ? 'text-status-fail' : 'text-ink-muted'}`}
              >
                {t(r.captionKey)}
              </span>
              {r.detail && (
                <span className="tabular text-ink-faint shrink-0 text-xs">{r.detail}</span>
              )}
            </div>
            <UptimeStrip slots={slots} pct={availability(slots)} />
          </li>
        )
      })}
    </ul>
  )
}
