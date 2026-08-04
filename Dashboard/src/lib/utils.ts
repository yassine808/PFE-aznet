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
