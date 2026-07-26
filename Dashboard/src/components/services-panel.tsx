import { useI18n } from '@/lib/i18n'
import { LiveDot } from '@/components/live-dot'
import { availability, timeline, useUptimeHistory, type Sample } from '@/lib/uptime'
import type { ServiceRow, ServiceState } from '@/lib/services'

const SLOT_CLASS: Record<ServiceState, string> = {
  ok: 'bg-status-ok',
  warn: 'bg-status-warn',
  fail: 'bg-status-fail',
  idle: 'bg-ink-faint/35',
}

/**
 * Status strip: one column per minute for the last hour.
 *
 * Columns are separated by a 1px surface gap so adjacent same-state slots stay
 * countable rather than merging into one bar. Unrecorded minutes render as an
 * empty track, never as "up" — absence of evidence is not evidence of uptime.
 */
function UptimeStrip({ samples, serviceKey }: { samples: Sample[]; serviceKey: string }) {
  const { t } = useI18n()
  const slots = timeline(samples, serviceKey)
  const pct = availability(slots)

  return (
    <div className="flex items-center gap-3">
      <div className="flex h-5 flex-1 items-stretch gap-px" role="img" aria-label={t('uptime.lastHour')}>
        {slots.map((s, i) => (
          <span
            key={i}
            className={`flex-1 rounded-[1px] ${s ? SLOT_CLASS[s] : 'bg-line/60'}`}
            title={s ? t(`svc.state.${s}`) : t('uptime.noRecord')}
          />
        ))}
      </div>
      <span className="tabular text-ink-faint w-9 shrink-0 text-end text-xs">{pct === null ? '—' : `${pct}%`}</span>
    </div>
  )
}

export function ServicesPanel({ rows }: { rows: ServiceRow[] }) {
  const { t } = useI18n()
  const samples = useUptimeHistory(rows)

  return (
    <ul className="divide-line flex flex-col divide-y">
      {rows.map((r) => (
        <li key={r.key} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
          <div className="flex items-baseline gap-3">
            <span className="translate-y-[3px]">
              <LiveDot tone={r.state} live={r.state === 'ok'} />
            </span>
            <span className="text-ink min-w-0 flex-1 truncate text-sm">{t(r.labelKey)}</span>
            <span className={`text-xs ${r.state === 'fail' ? 'text-status-fail' : 'text-ink-muted'}`}>
              {t(r.captionKey)}
            </span>
            {r.detail && <span className="tabular text-ink-faint shrink-0 text-xs">{r.detail}</span>}
          </div>
          <UptimeStrip samples={samples} serviceKey={r.key} />
        </li>
      ))}
    </ul>
  )
}
