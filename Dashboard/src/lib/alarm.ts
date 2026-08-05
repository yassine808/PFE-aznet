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

/**
 * One-shot chime for a newly arrived notification.
 *
 * Shares this file with the alarm because they are the same problem — WebAudio
 * refuses to make a sound before the first user gesture — and deliberately not
 * the same sound: the alarm is two flat bursts at one pitch (something is
 * wrong), the chime is a rising third (something arrived). A reader must be
 * able to tell them apart without looking at the screen.
 *
 * ponytail: a module-level context, not a hook — the caller is an effect that
 * fires on a poll, and there is only ever one browser tab's worth of audio.
 */
const chimeCtx: { current: AudioContext | null } = { current: null }
let gestured = false

if (typeof window !== 'undefined') {
  const arm = () => {
    gestured = true
  }
  window.addEventListener('pointerdown', arm, { once: true })
  window.addEventListener('keydown', arm, { once: true })
}

export function chime() {
  // Before the first click the browser blocks audio anyway; returning early
  // keeps a permanently-suspended context from being created and cached.
  if (!gestured) return
  try {
    if (!chimeCtx.current) {
      const Ctor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctor) return
      chimeCtx.current = new Ctor()
    }
    const ctx = chimeCtx.current
    void ctx.resume().catch(() => {})

    // E5 then G#5 — a rising major third, quiet and short.
    for (const [offset, freq] of [
      [0, 659.25],
      [0.11, 830.61],
    ] as const) {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.value = freq
      const t = ctx.currentTime + offset
      gain.gain.setValueAtTime(0.0001, t)
      gain.gain.exponentialRampToValueAtTime(0.09, t + 0.015)
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.32)
      osc.connect(gain).connect(ctx.destination)
      osc.start(t)
      osc.stop(t + 0.34)
    }
  } catch {
    // A blocked or unsupported audio stack must never break the notification
    // itself — the toast is the message, the sound is only the doorbell.
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