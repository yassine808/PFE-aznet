import { memo, useState } from 'react'
import { motion } from 'motion/react'
import { useI18n } from '@/lib/i18n'

export interface Tick {
  /** Minutes since midnight. */
  at: number
  flagged: boolean
  time: string
  technicien: string
  chantier: string
}

const HOURS = [0, 6, 12, 18, 24]

/**
 * A rug plot: one mark per report on a 24-hour axis.
 *
 * Marks are deliberately uniform in height. Varying height would imply a
 * magnitude that this data does not carry (most quantity cells are empty), and
 * a false encoding is worse than none. Occurrence and time are the whole story;
 * flagged state is carried by colour AND a cap marker, never colour alone.
 */
export const DayRibbon = memo(function DayRibbon({ ticks, dir }: { ticks: Tick[]; dir: 'ltr' | 'rtl' }) {
  const { t } = useI18n()
  const [hover, setHover] = useState<number | null>(null)

  const pct = (minutes: number) => {
    const clamped = Math.min(Math.max(minutes, 0), 1440)
    const p = (clamped / 1440) * 100
    return dir === 'rtl' ? 100 - p : p
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="relative h-28">
        {/* Recessive gridlines: hairline, never competing with the marks. */}
        {HOURS.map((h) => (
          <span
            key={h}
            className="bg-line absolute top-0 bottom-5 w-px"
            style={{ insetInlineStart: `${pct(h * 60)}%` }}
            aria-hidden="true"
          />
        ))}
        <span className="bg-line-strong absolute inset-x-0 bottom-5 h-px" aria-hidden="true" />

        {ticks.map((tick, i) => {
          const active = hover === i
          return (
            <div
              key={`${tick.at}-${i}`}
              className="absolute top-0 bottom-5 -translate-x-1/2 rtl:translate-x-1/2"
              style={{ insetInlineStart: `${pct(tick.at)}%` }}
            >
              {/* Hit target is far wider than the 3px mark. */}
              <button
                type="button"
                className="absolute inset-y-0 -inset-x-2.5 cursor-default"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                aria-label={`${tick.time} ${tick.technicien}`}
              />
              <motion.span
                className={`absolute bottom-0 w-[3px] rounded-full ${tick.flagged ? 'bg-status-warn' : 'bg-accent'}`}
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: '62%', opacity: active ? 1 : 0.9 }}
                transition={{ type: 'spring', stiffness: 100, damping: 20, delay: Math.min(i * 0.03, 0.35) }}
                aria-hidden="true"
              />
              {/* Cap marker: the secondary encoding that keeps flagged legible without colour. */}
              {tick.flagged && (
                <span
                  className="bg-status-warn ring-surface absolute bottom-[58%] size-2 -translate-x-1/2 rounded-full ring-2 rtl:translate-x-1/2"
                  style={{ insetInlineStart: '1.5px' }}
                  aria-hidden="true"
                />
              )}

              {active && (
                <div className="pointer-events-none absolute bottom-[72%] left-1/2 z-20 w-max -translate-x-1/2">
                  <div className="border-line bg-surface-raised edge rounded-lg border px-3 py-2 shadow-[0_12px_28px_-16px_oklch(0.146_0.008_245/0.5)]">
                    <p className="tabular text-ink text-xs font-medium">{tick.time}</p>
                    <p className="text-ink-muted mt-0.5 text-xs">{tick.technicien || '—'}</p>
                    {tick.chantier && <p className="text-ink-faint text-xs">{tick.chantier}</p>}
                  </div>
                </div>
              )}
            </div>
          )
        })}

        {/* Hour labels sit inside the plot frame so the axis reads as one object. */}
        {HOURS.map((h) => (
          <span
            key={`label-${h}`}
            className="tabular text-ink-faint absolute bottom-0 -translate-x-1/2 text-[0.6875rem] rtl:translate-x-1/2"
            style={{ insetInlineStart: `${pct(h * 60)}%` }}
          >
            {String(h).padStart(2, '0')}h
          </span>
        ))}

        {ticks.length === 0 && (
          <span className="text-ink-faint absolute inset-x-0 top-1/3 text-center text-xs">{t('ribbon.noneToday')}</span>
        )}
      </div>

      {/* Two states means a legend is mandatory: identity is never colour alone. */}
      <div className="text-ink-faint flex items-center gap-5 text-xs">
        <span className="flex items-center gap-2">
          <span className="bg-accent inline-block h-3 w-[3px] rounded-full" aria-hidden="true" />
          {t('ribbon.normal')}
        </span>
        <span className="flex items-center gap-2">
          <span className="relative inline-flex h-3 w-[3px] justify-center" aria-hidden="true">
            <span className="bg-status-warn h-full w-full rounded-full" />
            <span className="bg-status-warn ring-surface absolute -top-1 size-2 rounded-full ring-2" />
          </span>
          {t('metric.flagged')}
        </span>
      </div>
    </div>
  )
})
