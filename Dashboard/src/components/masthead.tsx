import { useState } from 'react'
import { motion } from 'motion/react'
import { SpeakerSimpleXIcon, SpeakerSimpleHighIcon } from '@phosphor-icons/react'
import { useI18n } from '@/lib/i18n'
import { useAlarm } from '@/lib/alarm'
import { LiveDot } from '@/components/live-dot'
import { cn } from '@/lib/utils'

export type SystemState = 'nominal' | 'degraded' | 'down'

/**
 * The one Committed surface in the system: a full-bleed slab that carries the day.
 * Healthy it is ink; degraded it takes the warning colour; down it goes red edge to
 * edge. A failure cannot be scrolled past or mistaken for decoration.
 */
export function Masthead({
  state,
  headline,
  headlineLabel,
  meta,
}: {
  state: SystemState
  headline: string
  headlineLabel: string
  meta: { label: string; value: string }[]
}) {
  const { t } = useI18n()
  const [muted, setMuted] = useState(false)
  const down = state === 'down'
  useAlarm(down, muted)

  // Attention is signalled by inverting the slab, not by hue: nominal is a dark
  // slab, degraded flips to a pale one in both themes, down is the only colour.
  const skin =
    state === 'down'
      ? 'bg-status-fail text-white'
      : state === 'degraded'
        ? 'bg-slate-100 text-slate-950 ring-1 ring-slate-300 ring-inset dark:ring-slate-400'
        : 'bg-slate-900 text-slate-50 dark:bg-slate-850'

  const stateLabel =
    state === 'down'
      ? t('status.unreachable')
      : state === 'degraded'
        ? t('state.degraded')
        : t('status.live')

  return (
    <motion.section
      layout
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className={cn(
        'edge relative overflow-hidden rounded-xl px-7 py-8',
        skin,
        down && 'alarm-flash',
      )}
      role={down ? 'alert' : undefined}
    >
      {down && (
        <button
          type="button"
          onClick={() => setMuted((m) => !m)}
          title={muted ? t('alert.unmute') : t('alert.mute')}
          aria-label={muted ? t('alert.unmute') : t('alert.mute')}
          className="absolute end-4 top-4 rounded-md p-1.5 text-white/80 ring-1 ring-white/30 transition-colors hover:text-white active:translate-y-px"
        >
          {muted ? <SpeakerSimpleXIcon size={15} /> : <SpeakerSimpleHighIcon size={15} />}
        </button>
      )}

      <div className="flex flex-wrap items-end justify-between gap-x-10 gap-y-6">
        <div>
          <p className="flex items-center gap-2 text-xs font-medium tracking-wide uppercase opacity-80">
            <LiveDot
              tone={state === 'down' ? 'fail' : state === 'degraded' ? 'ink' : 'ok'}
              live={state !== 'down'}
            />
            {stateLabel}
          </p>
          <p className="tabular mt-4 text-6xl leading-none font-medium tracking-tighter">
            {headline}
          </p>
          <p className="mt-2 text-sm opacity-70">{headlineLabel}</p>
        </div>

        <dl className="flex flex-wrap gap-x-8 gap-y-4">
          {meta.map((m) => (
            <div key={m.label}>
              <dt className="text-[0.6875rem] tracking-wide uppercase opacity-60">{m.label}</dt>
              <dd className="tabular mt-1 text-lg leading-none">{m.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </motion.section>
  )
}
