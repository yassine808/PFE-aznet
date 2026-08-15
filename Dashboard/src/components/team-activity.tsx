import { useMemo, useState } from 'react'
import { createUser, type Async, type History } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { daysAgoISO, parseISODay } from '@/lib/metrics'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

/**
 * What one account has done: headline counts, a 14-day graph, time per page and
 * the action timeline.
 *
 * Lifted out of the old `pages/team.tsx` when the org chart absorbed it. These
 * blocks are unchanged — only their trigger moved, from a chip in a flat list to
 * a box in the chart. They render for a directeur or a chef; a technician never
 * signs in, so `pages/equipe.tsx` shows them their channels and profile instead
 * rather than three panels that are permanently empty.
 */

/** Actions the director asked to count, in the order they matter. */
const HEADLINE = ['flag_cleared', 'report_edited', 'settings_saved', 'report_generated'] as const

/**
 * Actions shown before the panel asks whether you want the rest.
 *
 * The endpoint returns the whole audit trail, and rendering it made the detail
 * drawer several screens long for anyone who has used the dashboard for a
 * week — the profile and channel blocks under it became unreachable without a
 * long scroll past rows nobody was reading. Eight covers "what did they just
 * do", which is the question the panel is opened with; the rest is one click
 * away and never leaves the page.
 */
const RECENT_SHOWN = 8

function hhmm(seconds: number) {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

export function HistBlock({ hist }: { readonly hist: Async<History> }) {
  if (hist.error) return <ErrorState message={hist.error} onRetry={hist.reload} />
  if (hist.loading && !hist.data) return <Skeleton className="h-64" />
  if (hist.data) return <Activity data={hist.data} />
  return null
}

export function Activity({ data }: { readonly data: History }) {
  const { t, locale } = useI18n()
  const { settings } = useSettings()
  const [expanded, setExpanded] = useState(false)

  // 14 days, zero-filled here rather than in SQL: a day with no activity has to
  // show as a gap in the bars, not vanish and make the fortnight look shorter.
  const days = useMemo(() => {
    const found = new Map(data.daily.map((d) => [d.day, Number(d.n)]))
    return Array.from({ length: 14 }, (_, i) => {
      const key = daysAgoISO(13 - i)
      return { key, n: found.get(key) ?? 0 }
    })
  }, [data.daily])

  const peak = Math.max(1, ...days.map((d) => d.n))

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-wrap gap-x-10 gap-y-4">
        {HEADLINE.map((action) => (
          <div key={action} className="flex flex-col gap-0.5">
            <span className="text-ink tabular text-2xl">{data.totals[action] ?? 0}</span>
            <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
              {t(`team.count.${action}`)}
            </span>
          </div>
        ))}
        <div className="flex flex-col gap-0.5">
          <span className="text-ink tabular text-2xl">{hhmm(data.total_seconds)}</span>
          <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
            {t('team.totalTime')}
          </span>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
          {t('team.graph')}
        </h2>
        {/* Hand-built like every other chart here — no Recharts, per DESIGN.md. */}
        <div className="flex h-24 items-end gap-1">
          {days.map((d) => (
            <div key={d.key} className="group relative flex flex-1 flex-col justify-end">
              <div
                className={cn('rounded-t transition-colors', d.n > 0 ? 'bg-accent' : 'bg-line')}
                style={{ height: `${Math.max(2, (d.n / peak) * 100)}%` }}
              />
              <span className="text-ink-faint pointer-events-none absolute -top-5 left-1/2 -translate-x-1/2 text-[0.625rem] opacity-0 transition-opacity group-hover:opacity-100">
                {d.n}
              </span>
            </div>
          ))}
        </div>
        <div className="text-ink-faint flex justify-between text-[0.625rem]">
          <span>
            {/* parseISODay, not `new Date(iso)`: the bare form parses as UTC and
                labels the first bar with the wrong day west of the meridian. */}
            {parseISODay(days[0].key).toLocaleDateString(locale, {
              day: 'numeric',
              month: 'short',
            })}
          </span>
          <span>{t('team.today')}</span>
        </div>
      </section>

      {data.pages.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
            {t('team.timePerPage')}
          </h2>
          <ul className="flex flex-col gap-1">
            {data.pages.map((p) => (
              <li key={p.route} className="flex items-center gap-3 text-xs">
                <span className="text-ink-muted w-24 capitalize">{p.route}</span>
                <span className="bg-line h-1.5 flex-1 overflow-hidden rounded-full">
                  <span
                    className="bg-accent block h-full rounded-full"
                    style={{
                      width: `${(Number(p.seconds) / Number(data.pages[0].seconds || 1)) * 100}%`,
                    }}
                  />
                </span>
                <span className="text-ink-faint tabular w-16 text-end">
                  {hhmm(Number(p.seconds))}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="flex flex-col gap-2">
        <h2 className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
          {t('team.recent')}
        </h2>
        {data.actions.length === 0 ? (
          <EmptyState body={t('team.noActions')} />
        ) : (
          <ul className="flex flex-col">
            {(expanded ? data.actions : data.actions.slice(0, RECENT_SHOWN)).map((a) => (
              <li
                key={a.id}
                className="border-line flex flex-wrap items-baseline gap-x-3 border-b py-2 text-xs last:border-b-0"
              >
                <span className="text-ink-faint tabular w-32 shrink-0">
                  {new Date(a.created_at).toLocaleString(locale, {
                    day: '2-digit',
                    month: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: settings.timeFormat === '12h',
                  })}
                </span>
                <span className="text-ink">{t(`team.action.${a.action}`)}</span>
                {a.target && <span className="text-ink-muted">{a.target}</span>}
                {/* The before → after that PATCH /reports now captures. */}
                {(a.before_val || a.after_val) && (
                  <span className="text-ink-faint">
                    {a.before_val || '∅'} → {a.after_val || '∅'}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        {data.actions.length > RECENT_SHOWN && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            className="text-accent focus-visible:ring-accent cursor-pointer self-start rounded-md py-1 text-xs outline-none focus-visible:ring-2"
          >
            {expanded
              ? t('team.showLess')
              : t('team.showMore', { count: data.actions.length - RECENT_SHOWN })}
          </button>
        )}
      </section>
    </div>
  )
}

/**
 * Credentials for someone who is already on the chart.
 *
 * `name` is passed in and read-only: the "+" created the person, this only adds
 * their login. Editing it here would credential a *different* human — the API
 * matches an account to a person by name.
 */
export function GrantAccessForm({
  name,
  onDone,
}: {
  readonly name: string
  readonly onDone: () => void
}) {
  const { t } = useI18n()
  const [values, setValues] = useState({ email: '', password: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await createUser({ ...values, name })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
      {(['email', 'password'] as const).map((field) => (
        <label key={field} className="flex min-w-40 flex-col gap-1.5">
          <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
            {t(`team.${field}`)}
          </span>
          <input
            type={field === 'email' ? 'email' : 'password'}
            value={values[field]}
            onChange={(e) => setValues((v) => ({ ...v, [field]: e.target.value }))}
            required
            autoComplete={field === 'password' ? 'new-password' : undefined}
            className="border-line focus:border-accent focus-visible:ring-accent text-ink bg-canvas rounded-md border px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-2"
          />
        </label>
      ))}
      <button
        type="submit"
        disabled={busy}
        className="bg-accent focus-visible:ring-accent cursor-pointer rounded-md px-3.5 py-2 text-sm text-white transition-transform outline-none active:translate-y-px focus-visible:ring-2 disabled:opacity-50"
      >
        {t('equipe.grant')}
      </button>
      {error && <p className="text-status-fail w-full text-xs break-all">{error}</p>}
    </form>
  )
}
