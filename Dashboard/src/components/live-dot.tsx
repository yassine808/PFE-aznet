import { memo } from 'react'
import { motion } from 'motion/react'

type Tone = 'ok' | 'warn' | 'fail' | 'queued' | 'idle' | 'ink'

const TONE_CLASS: Record<Tone, string> = {
  ok: 'bg-status-ok',
  warn: 'bg-status-warn',
  fail: 'bg-status-fail',
  queued: 'bg-status-queued',
  idle: 'bg-ink-faint',
  // Inherits the surrounding text colour: for use on inverted slabs, where a
  // fixed status colour can land invisible against the slab.
  ink: 'bg-current',
}

/**
 * The only perpetually animating primitive in the shell.
 * It pulses strictly while `live` is true, so movement means "this is happening now".
 * Memoized and isolated so the loop never re-renders anything around it.
 */
export const LiveDot = memo(function LiveDot({ tone, live = false }: { tone: Tone; live?: boolean }) {
  return (
    <span className="relative inline-flex size-2 shrink-0" aria-hidden="true">
      <span className={`size-2 rounded-full ${TONE_CLASS[tone]}`} />
      {live && (
        <motion.span
          className={`absolute inset-0 rounded-full ${TONE_CLASS[tone]}`}
          animate={{ scale: [1, 2.4], opacity: [0.5, 0] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: 'easeOut' }}
        />
      )}
    </span>
  )
})
