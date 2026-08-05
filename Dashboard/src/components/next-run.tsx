import { useMemo } from 'react'
import { ClockCountdownIcon } from '@phosphor-icons/react'
import { api, useApi } from '@/lib/api'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { nextDailyRun, nextWeeklyRun, relativeParts } from '@/lib/schedule'

/**
 * When this report goes out on its own.
 *
 * The generate button on these pages produces a report *now*, signed by the
 * account that pressed it — which is easy to read as "reports only exist if
 * someone makes one". They do not: the scheduler mails one on a stored
 * schedule, and until this line existed the only way to learn that was to
 * open the Automation page. One sentence under the graph closes that gap.
 *
 * The hour comes from `GET /settings` — the same row `api/app/jobs.py` reads on
 * every tick — so an edited time is reflected here without a second source of
 * truth. `useApi` serves it from the module cache, so this costs one shared
 * request per session rather than one per page visit.
 */
export function NextRun({ kind }: { readonly kind: 'daily' | 'weekly' }) {
  const { t, locale } = useI18n()
  const { settings: prefs } = useSettings()
  const stored = useApi('settings', api.settings)
  const s = stored.data?.settings

  const when = useMemo(() => {
    if (!s) return null
    return kind === 'daily'
      ? nextDailyRun(s.daily_time)
      : nextWeeklyRun(s.weekly_day, s.weekly_time)
    // Recomputed when the stored schedule changes. Not on a timer: this is a
    // date, not a countdown, and the page is not open long enough to drift.
  }, [s, kind])

  // Silent while loading and silent on error. A schedule line that guesses is
  // worse than no schedule line — the operator would plan around the guess.
  if (!when) return null

  const dt = new Intl.DateTimeFormat(intlLocaleOf(locale), {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
    hour12: prefs.timeFormat === '12h',
  })
  const rel = new Intl.RelativeTimeFormat(intlLocaleOf(locale), { numeric: 'auto' })
  const [value, unit] = relativeParts(when)

  return (
    <p className="text-ink-faint flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
      <ClockCountdownIcon size={14} className="shrink-0" />
      <span>{t('schedule.next')}</span>
      <span className="text-ink-muted tabular">{dt.format(when)}</span>
      <span aria-hidden>·</span>
      <span>{rel.format(value, unit)}</span>
    </p>
  )
}
