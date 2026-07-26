import { memo } from 'react'

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
 * The pulse is a pure CSS animation, deliberately.
 *
 * Driven by Framer it restarted on every parent re-render, and with polling
 * every 15-60s across several rows that produced a visible stutter. CSS
 * keyframes live outside React entirely, so a re-render cannot interrupt them.
 */
export const LiveDot = memo(function LiveDot({ tone, live = false }: { tone: Tone; live?: boolean }) {
  return (
    <span className="relative inline-flex size-2 shrink-0 align-middle" aria-hidden="true">
      {live && <span className={`live-ping absolute inset-0 rounded-full ${TONE_CLASS[tone]}`} />}
      <span className={`relative size-2 rounded-full ${TONE_CLASS[tone]}`} />
    </span>
  )
})
