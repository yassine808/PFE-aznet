import { useRef } from 'react'
import { CalendarBlankIcon, CaretLeftIcon, CaretRightIcon } from '@phosphor-icons/react'
import { parseISODay } from '@/lib/metrics'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { cn } from '@/lib/utils'

const DAY_MS = 86_400_000

// `2026-08-05` → local `Date`, invalid values fall back to today. Never
// `new Date(iso)`, which parses as UTC and shifts the day.
const parse = parseISODay

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Monday of the week containing `d` — the scheduler's week starts there too. */
function monday(d: Date): Date {
  const out = new Date(d)
  out.setDate(out.getDate() - ((out.getDay() + 6) % 7))
  out.setHours(0, 0, 0, 0)
  return out
}

/**
 * Step a period, jump to a specific one, or come back to now.
 *
 * The old control was a bare `<input type="date">` with a label above it. It
 * worked, but reading it meant parsing `2026-08-05` and moving one day meant
 * opening a calendar — so the two things actually done on these pages (walk
 * back through the week, get back to today) were the two most expensive.
 *
 * The native input is still the only date control here — a picker library would
 * be a dependency for zero gain — it is just no longer the whole interface. It
 * sits behind the middle button, which shows the day the way the reader's
 * locale writes it and opens the calendar with `showPicker()`. Browsers without
 * that method fall through to focusing the input, which opens the same calendar
 * on click. Both are the platform's own picker, keyboard and screen reader
 * included.
 */
export function PeriodPicker({
  mode,
  value,
  onChange,
  className,
}: {
  /** `day` steps by one day; `week` steps by seven and snaps to that week's Monday. */
  readonly mode: 'day' | 'week'
  /** ISO day. In `week` mode this is the week's Monday. */
  readonly value: string
  readonly onChange: (isoDay: string) => void
  readonly className?: string
}) {
  const { t, locale } = useI18n()
  const input = useRef<HTMLInputElement>(null)

  const current = parse(value)
  const step = mode === 'week' ? 7 : 1
  const snap = (d: Date) => (mode === 'week' ? monday(d) : d)

  const shift = (days: number) => {
    onChange(iso(snap(new Date(current.getTime() + days * DAY_MS))))
  }

  const intl = intlLocaleOf(locale)
  const long = new Intl.DateTimeFormat(intl, { weekday: 'short', day: 'numeric', month: 'long' })
  const short = new Intl.DateTimeFormat(intl, { day: 'numeric', month: 'short' })

  const label =
    mode === 'week'
      ? `${short.format(current)} – ${short.format(new Date(current.getTime() + 6 * DAY_MS))}`
      : long.format(current)

  const now = snap(new Date())
  const isNow = iso(now) === value

  // A calendar cannot be opened from a `display: none` input, and a `sr-only`
  // one is off-screen — so it is sized to nothing *inside* the button instead,
  // where the browser still anchors the popup to the visible control.
  const openPicker = () => {
    const el = input.current
    if (!el) return
    if (typeof el.showPicker === 'function') el.showPicker()
    else el.focus()
  }

  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      <div className="border-line flex items-center rounded-md border">
        <button
          type="button"
          onClick={() => shift(-step)}
          aria-label={t(mode === 'week' ? 'period.prevWeek' : 'period.prevDay')}
          className="text-ink-faint hover:text-ink flex size-8 items-center justify-center rounded-s-md transition-colors active:translate-y-px"
        >
          <CaretLeftIcon size={14} className="rtl:rotate-180" />
        </button>

        <button
          type="button"
          onClick={openPicker}
          aria-label={t('period.pick')}
          className="border-line text-ink hover:bg-surface relative flex items-center gap-2 border-x px-3 py-1.5 text-sm transition-colors"
        >
          <CalendarBlankIcon size={14} className="text-ink-faint shrink-0" />
          <span className="tabular whitespace-nowrap">{label}</span>
          <input
            ref={input}
            type="date"
            value={value}
            onChange={(e) => e.target.value && onChange(iso(snap(parse(e.target.value))))}
            tabIndex={-1}
            aria-hidden
            className="pointer-events-none absolute bottom-0 start-1/2 size-0 opacity-0"
          />
        </button>

        <button
          type="button"
          onClick={() => shift(step)}
          aria-label={t(mode === 'week' ? 'period.nextWeek' : 'period.nextDay')}
          className="text-ink-faint hover:text-ink flex size-8 items-center justify-center rounded-e-md transition-colors active:translate-y-px"
        >
          <CaretRightIcon size={14} className="rtl:rotate-180" />
        </button>
      </div>

      {/* Hidden rather than disabled when it would do nothing: a permanently
          greyed control is a promise the interface never keeps. */}
      {!isNow && (
        <button
          type="button"
          onClick={() => onChange(iso(now))}
          className="text-ink-faint hover:text-ink rounded-md px-2 py-1.5 text-xs transition-colors active:translate-y-px"
        >
          {t(mode === 'week' ? 'period.thisWeek' : 'period.today')}
        </button>
      )}
    </div>
  )
}
