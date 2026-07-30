import { useEffect, useRef } from 'react'

const BEEP_MS = 6_000

/**
 * Audible alarm while the API is unreachable.
 *
 * ponytail: WebAudio oscillator, not an mp3 asset — two sine bursts is less code
 * than shipping, loading and unlocking a file. Browsers refuse to start audio
 * before a user gesture, so the context is created lazily and resumed on each
 * beep; in practice the operator has clicked something long before the API dies.
 */
function beep(ctxRef: { current: AudioContext | null }) {
  if (!ctxRef.current) {
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!Ctor) return
    ctxRef.current = new Ctor()
  }
  const ctx = ctxRef.current
  void ctx.resume()

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
}

export function useAlarm(active: boolean, muted: boolean) {
  const ctxRef = useRef<AudioContext | null>(null)

  useEffect(() => {
    if (!active || muted) return
    beep(ctxRef)
    const timer = window.setInterval(() => beep(ctxRef), BEEP_MS)
    return () => window.clearInterval(timer)
  }, [active, muted])

  useEffect(() => () => void ctxRef.current?.close(), [])
}
