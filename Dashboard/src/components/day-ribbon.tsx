import { memo } from 'react'
import { motion } from 'motion/react'
import { useI18n } from '@/lib/i18n'

export interface Tick {
  /** Minutes since midnight. */
  at: number
  flagged: boolean
  label: string
}

/**
 * A 24-hour axis with one tick per report: the day as a shape rather than a number.
 * Reading the rhythm of when the crew reports is the point; the count is already
 * in the masthead.
 */
export const DayRibbon = memo(function DayRibbon({ ticks, dir }: { ticks: Tick[]; dir: 'ltr' | 'rtl' }) {
  const { t } = useI18n()
  const HOURS = [0, 6, 12, 18, 24]

  const pct = (minutes: number) => {
    const clamped = Math.min(Math.max(minutes, 0), 1440)
    const p = (clamped / 1440) * 100
    return dir === 'rtl' ? 100 - p : p
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="border-line relative h-16 border-y">
        {/* Hour gridlines. Hairlines only: the ticks must stay the loudest thing here. */}
        {HOURS.map((h) => (
          <span
            key={h}
            className="bg-line absolute top-0 bottom-0 w-px"
            style={{ insetInlineStart: `${pct(h * 60)}%` }}
            aria-hidden="true"
          />
        ))}

        {ticks.map((tick, i) => (
          <motion.span
            key={`${tick.at}-${i}`}
            className={`absolute bottom-0 w-0.5 rounded-full ${tick.flagged ? 'bg-status-warn' : 'bg-accent'}`}
            style={{ insetInlineStart: `${pct(tick.at)}%` }}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: tick.flagged ? '100%' : '68%', opacity: 1 }}
            transition={{ type: 'spring', stiffness: 100, damping: 20, delay: Math.min(i * 0.03, 0.4) }}
            title={tick.label}
          />
        ))}

        {ticks.length === 0 && (
          <span className="text-ink-faint absolute inset-0 flex items-center justify-center text-xs">
            {t('ribbon.noneToday')}
          </span>
        )}
      </div>

      <div className="text-ink-faint relative h-4 text-[0.6875rem]">
        {HOURS.map((h) => (
          <span
            key={h}
            className="tabular absolute -translate-x-1/2 rtl:translate-x-1/2"
            style={{ insetInlineStart: `${pct(h * 60)}%` }}
          >
            {String(h).padStart(2, '0')}h
          </span>
        ))}
      </div>
    </div>
  )
})
