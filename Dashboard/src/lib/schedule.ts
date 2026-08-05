/**
 * When the scheduler will next send a report, computed in the browser.
 *
 * `GET /jobs` already returns a `schedule` string, but it is written in French
 * by `jobs._schedule_label` for the Automation page's own timeline — it is a
 * sentence, not a timestamp, so it can be neither localised nor counted down
 * from. These two functions read the same three stored values the scheduler
 * reads (`daily_time`, `weekly_day`, `weekly_time`) and return a real `Date`,
 * which `Intl.DateTimeFormat` then renders in whatever locale is on screen.
 *
 * The rules are `api/app/jobs.py`'s, mirrored deliberately and narrowly:
 * the daily mail runs Monday to Saturday and never on Sunday, and the weekly
 * mail runs on one weekday counted the way `datetime.weekday()` counts —
 * 0 = Monday. JavaScript's `getDay()` counts from Sunday, so every comparison
 * here goes through `weekdayMon`, never through `getDay()` directly.
 */

/** `datetime.weekday()`'s numbering: 0 = Monday … 6 = Sunday. */
function weekdayMon(d: Date): number {
  return (d.getDay() + 6) % 7
}

/** `"18:30"` → `[18, 30]`, falling back to the scheduler's own default. */
function hhmm(value: string | undefined, fallback: [number, number]): [number, number] {
  const m = /^(\d{1,2}):(\d{2})$/.exec((value ?? '').trim())
  if (!m) return fallback
  const h = Number(m[1])
  const min = Number(m[2])
  if (h > 23 || min > 59) return fallback
  return [h, min]
}

function at(day: Date, [h, m]: [number, number]): Date {
  const d = new Date(day)
  d.setHours(h, m, 0, 0)
  return d
}

/** Next daily-report mail: Mon–Sat at `daily_time`, Sunday skipped. */
export function nextDailyRun(time: string | undefined, from: Date = new Date()): Date {
  const clock = hhmm(time, [18, 30])
  // At most 8 candidates: today, then a full week. One of them always lands on
  // a Monday-to-Saturday day that has not passed yet.
  for (let i = 0; i < 8; i += 1) {
    const day = new Date(from)
    day.setDate(day.getDate() + i)
    const when = at(day, clock)
    if (weekdayMon(when) === 6) continue // Sunday: no site work, no report
    if (when > from) return when
  }
  return at(from, clock)
}

/** Next weekly-report mail: `weekly_day` (0 = Monday) at `weekly_time`. */
export function nextWeeklyRun(
  day: number | undefined,
  time: string | undefined,
  from: Date = new Date(),
): Date {
  const target = Math.max(0, Math.min(6, Number.isFinite(day) ? Number(day) : 4))
  const clock = hhmm(time, [17, 0])
  for (let i = 0; i < 8; i += 1) {
    const d = new Date(from)
    d.setDate(d.getDate() + i)
    const when = at(d, clock)
    if (weekdayMon(when) === target && when > from) return when
  }
  return at(from, clock)
}

/**
 * Coarse "in 3 h", "in 2 days" distance, as `Intl.RelativeTimeFormat` units.
 *
 * Coarse on purpose: a report due tonight is useful as "in 5 hours" and noise
 * as "in 4 hours 52 minutes", and a per-second countdown on a page nobody is
 * watching is a repaint budget spent on nothing.
 */
export function relativeParts(target: Date, from: Date = new Date()): [number, Intl.RelativeTimeFormatUnit] {
  const minutes = Math.round((target.getTime() - from.getTime()) / 60_000)
  if (Math.abs(minutes) < 60) return [minutes, 'minute']
  const hours = Math.round(minutes / 60)
  if (Math.abs(hours) < 24) return [hours, 'hour']
  return [Math.round(hours / 24), 'day']
}
