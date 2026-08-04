import { useEffect, useRef, useState } from 'react'

const BEEP_MS = 6_000

/**
 * Audible alarm while the API is unreachable.
 *
 * ponytail: WebAudio oscillator, not an mp3 asset — two sine bursts is less code
 * than shipping, loading and unlocking a file.
 */
function beep(ctxRef: { current: AudioContext | null }) {
  try {
    if (!ctxRef.current) {
      const Ctor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctor) return
      ctxRef.current = new Ctor()
    }
    const ctx = ctxRef.current
    void ctx.resume().catch(() => {})

    // Two short bursts: one tone reads as a notification, two as an alarm.
    for (const offset of [0, 0.28]) {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.value = 880
      const t = ctx.currentTime + offset
      // Ramped, not gated: an instant cut produces an audible click.
      gain.gain.setValueAtTime(0.0001, t)
      gain.gain.exponentialRampToValueAtTime(0.14, t + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.18)
      osc.connect(gain).connect(ctx.destination)
      osc.start(t)
      osc.stop(t + 0.2)
    }
  } catch {
    // Browsers refuse audio before the first user gesture; when the API dies
    // before anyone clicked, the alarm must not throw either.
  }
}

export function useAlarm(active: boolean, muted: boolean) {
  const ctxRef = useRef<AudioContext | null>(null)
  const [armed, setArmed] = useState(false)

  // WebAudio contexts created before any user gesture are permanently stuck in
  // a blocked state, so the alarm only starts after the first click/keypress.
  useEffect(() => {
    if (armed) return
    const arm = () => setArmed(true)
    window.addEventListener('pointerdown', arm, { once: true })
    window.addEventListener('keydown', arm, { once: true })
    return () => {
      window.removeEventListener('pointerdown', arm)
      window.removeEventListener('keydown', arm)
    }
  }, [armed])

  useEffect(() => {
    if (!active || muted || !armed) return
    beep(ctxRef)
    const timer = window.setInterval(() => beep(ctxRef), BEEP_MS)
    return () => window.clearInterval(timer)
  }, [active, muted, armed])

  useEffect(() => () => void ctxRef.current?.close(), [])
}