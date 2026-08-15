import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Copy text to the clipboard with a legacy fallback.
 *
 * `navigator.clipboard` only exists in secure contexts; behind plain HTTP it is
 * undefined and the copy button silently did nothing. execCommand is deprecated
 * but still the only path that works everywhere, so it catches that case.
 */
export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // Permission denied or busy: fall through to the legacy path.
    }
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.focus()
  ta.select()
  try {
    // Deprecated on purpose: the only copy path in a non-secure context.
    document.execCommand('copy') // NOSONAR
  } finally {
    ta.remove()
  }
}

/**
 * A Moroccan mobile as the channel stores it: 12 digits, `2126…` / `2127…`.
 *
 * Mirrors `logs.normalize_external_id` on the API, which is the authority —
 * this copy exists so the Team form shows the operator what will be saved
 * before they submit, not so the browser can decide the stored form.
 * Anything that is not a recognisable Moroccan number (a Telegram chat id, a
 * foreign number) is returned untouched: guessing there would corrupt an id
 * that was already correct.
 */
export function toMsisdn(raw: string): string {
  const digits = raw.replace(/\D/g, '')
  if (/^212[67]\d{8}$/.test(digits)) return digits
  if (/^2120[67]\d{8}$/.test(digits)) return `212${digits.slice(4)}` // +212 (0)6…
  if (/^00212[67]\d{8}$/.test(digits)) return digits.slice(2)
  if (/^0[67]\d{8}$/.test(digits)) return `212${digits.slice(1)}`
  if (/^[67]\d{8}$/.test(digits)) return `212${digits}`
  return raw.trim()
}

/**
 * The same number as a Moroccan reads it: `212661234567` → `06 61 23 45 67`.
 *
 * Display only — the stored id never changes. A Telegram id or anything that
 * is not a Moroccan mobile comes back untouched, because a chat id split into
 * pairs of digits would read as a phone number that does not exist.
 */
export function formatPhone(id: string | null | undefined): string {
  if (!id) return ''
  const d = id.replace(/\D/g, '')
  if (!/^212[67]\d{8}$/.test(d)) return id
  const local = `0${d.slice(3)}` // 0612345678
  return `${local.slice(0, 2)} ${local.slice(2, 4)} ${local.slice(4, 6)} ${local.slice(6, 8)} ${local.slice(8)}`
}
