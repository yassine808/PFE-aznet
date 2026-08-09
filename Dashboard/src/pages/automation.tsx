import { useEffect, useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import {
  ArrowClockwiseIcon,
  BellRingingIcon,
  BroomIcon,
  CalendarBlankIcon,
  CheckIcon,
  EnvelopeSimpleIcon,
  PaperPlaneTiltIcon,
  PlusIcon,
  TrashIcon,
  UserFocusIcon,
  WarningCircleIcon,
} from '@phosphor-icons/react'
import {
  api,
  putSettings,
  runJob,
  sendTestMail,
  useApi,
  type Async,
  type AppSettings,
  type JobStatus,
} from '@/lib/api'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

// The four fields this form edits. `stt_chain` is deliberately absent even
// though AppSettings has it: the save PUTs this whole object, and the director
//'s live STT order lives in a different panel — a whole-object save here must
// not reset it to a default it never chose.
type EditableSettings = Required<Omit<AppSettings, 'stt_chain'>>
const DEFAULTS: EditableSettings = {
  daily_time: '18:30',
  weekly_day: 4,
  weekly_time: '17:00',
  emails: [],
}

// Icon per job, so the rows are told apart at a glance rather than read.
const JOB_ICONS: Record<string, typeof BroomIcon> = {
  sheet_queue: ArrowClockwiseIcon,
  prune_logs: BroomIcon,
  profiles: UserFocusIcon,
  daily_report: EnvelopeSimpleIcon,
  weekly_report: CalendarBlankIcon,
  reminders: BellRingingIcon,
}

// Order shown to the operator: the two mails they care about first, plumbing last.
const JOB_ORDER = ['daily_report', 'weekly_report', 'reminders', 'sheet_queue', 'profiles', 'prune_logs']


function Band({
  title,
  hint,
  children,
}: {
  readonly title: string
  readonly hint?: string
  readonly children: React.ReactNode
}) {
  return (
    <section className="flex min-w-0 flex-col gap-4">
      <div className="border-line flex flex-col gap-1 border-b pb-2">
        <h2 className="text-ink-faint text-[0.6875rem] font-medium tracking-wide uppercase">
          {title}
        </h2>
        {hint && <p className="text-ink-faint max-w-[75ch] text-xs">{hint}</p>}
      </div>
      {children}
    </section>
  )
}

const PLAN_HOURS = [0, 6, 12, 18, 24]

/**
 * Minutes since midnight for a job, or null when it has no fixed hour.
 *
 * Read out of `job.schedule` rather than mirrored from the scheduler's own
 * constants: the API builds that label itself (`jobs._schedule_label`) and
 * always writes ASCII digits, whatever locale the dashboard is in. Duplicating
 * NIGHTLY_HOUR here would be a second copy of a number that already drifted
 * once between Python and this page.
 */
function scheduledAt(job: JobStatus): number | null {
  const m = /(\d{1,2}):(\d{2})/.exec(job.schedule)
  if (!m) return null
  return Number(m[1]) * 60 + Number(m[2])
}

/**
 * The day, on one axis.
 *
 * The schedules were six sentences the operator had to read and assemble into
 * a mental timeline ("nightly at 03:00", "Monday to Saturday at 18:30", "every
 * five minutes"). This is the same 24-hour axis the Day Ribbon already uses for
 * reports, so "when does this machine act" is answered by looking rather than
 * by reading. Jobs with no fixed hour are not plotted — a tick would claim a
 * time they do not have — they are named underneath as continuous.
 */
function DayPlan({ jobs }: { readonly jobs: JobStatus[] }) {
  const { t, dir } = useI18n()

  /**
   * Where "now" sits on the axis, repainted once a minute.
   *
   * Without it the axis showed a day in the abstract and the operator still had
   * to find themselves on it before it meant anything. A needle turns the same
   * drawing into "the report goes out in two hours". A minute is the finest
   * step the axis can actually resolve — a second-by-second timer would repaint
   * sixty times for one pixel.
   */
  const [nowMinutes, setNowMinutes] = useState(() => {
    const d = new Date()
    return d.getHours() * 60 + d.getMinutes()
  })
  useEffect(() => {
    const id = window.setInterval(() => {
      const d = new Date()
      setNowMinutes(d.getHours() * 60 + d.getMinutes())
    }, 60_000)
    return () => window.clearInterval(id)
  }, [])

  const pct = (minutes: number) => {
    const p = (Math.min(Math.max(minutes, 0), 1440) / 1440) * 100
    return dir === 'rtl' ? 100 - p : p
  }
  // Clustered by minute, not one marker per job: the profile rebuild and the log
  // prune both fire at 03:00, and drawn independently the second sat exactly on
  // top of the first — the axis showed four nightly jobs as three.
  const clusters = new Map<number, JobStatus[]>()
  for (const job of jobs) {
    const at = scheduledAt(job)
    if (at === null) continue
    clusters.set(at, [...(clusters.get(at) ?? []), job])
  }
  const timed = [...clusters.entries()].sort((a, b) => a[0] - b[0])
  const continuous = jobs.filter((job) => scheduledAt(job) === null)
  // The next cluster to fire, wrapping past midnight — the one thing on this
  // axis worth emphasising, and the answer to "what happens next?".
  const next = timed.find(([at]) => at >= nowMinutes)?.[0] ?? timed[0]?.[0] ?? null

  return (
    <div className="flex flex-col gap-3">
      <div className="relative h-14">
        {/* Night, as a tonal wash rather than a labelled region: the three
            nightly jobs cluster at 03:00 and it should be obvious at a glance
            that they run while nobody is on site. */}
        <span
          aria-hidden
          className="bg-ink/[0.03] dark:bg-ink/[0.06] absolute inset-y-0 rounded-sm"
          style={{ insetInlineStart: `${pct(0)}%`, inlineSize: `${(6 / 24) * 100}%` }}
        />
        <span
          aria-hidden
          className="bg-ink/[0.03] dark:bg-ink/[0.06] absolute inset-y-0 rounded-sm"
          style={{ insetInlineStart: `${pct(20 * 60)}%`, inlineSize: `${(4 / 24) * 100}%` }}
        />

        {/* Recessive gridlines, same hairline language as the Day Ribbon. */}
        {PLAN_HOURS.map((h) => (
          <span
            key={h}
            aria-hidden
            className="bg-line absolute inset-y-0 w-px"
            style={{ insetInlineStart: `${pct(h * 60)}%` }}
          />
        ))}

        {/* Now. The one accented thing on the axis — DESIGN.md's Ten Percent
            Rule means the marks cannot all shout, and this is the mark that
            makes every other one legible. */}
        <span
          aria-hidden
          className="bg-accent absolute inset-y-0 w-px"
          style={{ insetInlineStart: `${pct(nowMinutes)}%` }}
        />
        <span
          className="bg-accent absolute top-0 size-1.5 -translate-x-1/2 rounded-full rtl:translate-x-1/2"
          style={{ insetInlineStart: `${pct(nowMinutes)}%` }}
        >
          <span className="sr-only">
            {t('automation.plan.now', {
              time: `${String(Math.floor(nowMinutes / 60)).padStart(2, '0')}:${String(nowMinutes % 60).padStart(2, '0')}`,
            })}
          </span>
        </span>

        {timed.map(([at, group]) => {
          const label = group
            .map((job) => `${t(`automation.job.${job.name}`)} — ${job.schedule}`)
            .join(' · ')
          const isNext = at === next
          return (
            <span
              key={at}
              title={label}
              className="absolute top-0 flex -translate-x-1/2 flex-col items-center gap-1 rtl:translate-x-1/2"
              style={{ insetInlineStart: `${pct(at)}%` }}
            >
              <span className="flex items-center gap-1">
                {group.map((job) => {
                  const Icon = JOB_ICONS[job.name] ?? ArrowClockwiseIcon
                  return (
                    <span
                      key={job.name}
                      className={cn(
                        'flex size-7 items-center justify-center rounded-full border transition-colors',
                        // Next up reads through weight, not through a second
                        // accent: the needle already owns the accent here.
                        isNext
                          ? 'border-ink-faint bg-surface text-ink'
                          : 'border-line bg-surface text-ink-faint',
                      )}
                    >
                      <Icon size={13} weight={isNext ? 'bold' : 'regular'} />
                    </span>
                  )
                })}
              </span>
              <span
                className={cn(
                  'tabular text-[0.625rem]',
                  isNext ? 'text-ink-muted' : 'text-ink-faint',
                )}
              >
                {String(Math.floor(at / 60)).padStart(2, '0')}:
                {String(at % 60).padStart(2, '0')}
              </span>
              <span className="sr-only">{label}</span>
            </span>
          )
        })}
      </div>

      <div className="relative h-4">
        {PLAN_HOURS.map((h) => (
          <span
            key={h}
            aria-hidden
            className="tabular text-ink-faint absolute top-0 -translate-x-1/2 text-[0.625rem] rtl:translate-x-1/2"
            style={{ insetInlineStart: `${pct(h * 60)}%` }}
          >
            {String(h % 24).padStart(2, '0')}
          </span>
        ))}
      </div>

      {continuous.length > 0 && (
        <p className="text-ink-faint flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <span>{t('automation.plan.continuous')}</span>
          {continuous.map((job) => (
            <span key={job.name} className="text-ink-muted">
              {t(`automation.job.${job.name}`)} ({job.schedule})
            </span>
          ))}
        </p>
      )}
    </div>
  )
}

/**
 * "il y a 4 min" from an ISO timestamp.
 *
 * Relative rather than absolute because the question an operator actually asks
 * is "did this run recently?", and answering it from "2026-07-29T18:30:04"
 * makes them do the subtraction themselves.
 */
function useAgo() {
  const { locale } = useI18n()
  return useMemo(() => {
    const rtf = new Intl.RelativeTimeFormat(intlLocaleOf(locale), { numeric: 'auto' })
    return (iso: string) => {
      const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
      if (seconds < 60) return rtf.format(-seconds, 'second')
      if (seconds < 3600) return rtf.format(-Math.round(seconds / 60), 'minute')
      if (seconds < 86_400) return rtf.format(-Math.round(seconds / 3600), 'hour')
      return rtf.format(-Math.round(seconds / 86_400), 'day')
    }
  }, [locale])
}

/**
 * Plain-French outcome for one run.
 *
 * The API returns a different result shape per job, and the earlier version of
 * this panel printed it as raw JSON. That is unreadable for the people this
 * dashboard is for, so each job gets one sentence. The keys carry the counts;
 * anything unrecognised falls back to the raw payload rather than to silence.
 */
function useOutcome() {
  const { t } = useI18n()
  return (job: JobStatus): string | null => {
    const last = job.last
    if (!last) return null
    if (!last.ok) return last.error ?? t('automation.job.failed')
    const r = (last.result ?? {}) as Record<string, never>
    const n = (key: string) => Number(r[key] ?? 0)
    switch (job.name) {
      case 'daily_report':
      case 'weekly_report': {
        const sent = (r['sent_to'] as unknown as string[]) ?? []
        if (!sent.length) return t('automation.out.noReports')
        return t('automation.out.mailed', { count: sent.length, rows: n('rows') })
      }
      case 'sheet_queue': {
        const failed = ((r['failed'] as unknown as unknown[]) ?? []).length
        if (!n('pending')) return t('automation.out.queueEmpty')
        return t('automation.out.queueDrained', { written: n('written'), failed })
      }
      case 'reminders':
        if (!n('due')) return t('automation.out.remindersNone')
        return t('automation.out.reminders', {
          due: n('due'), notified: n('notified'), emailed: n('emailed'),
        })
      case 'profiles':
        return t('automation.out.profiles', { refreshed: n('refreshed'), total: n('persons') })
      case 'prune_logs':
        return t('automation.out.pruned', { count: n('logs_deleted') + n('samples_deleted') })
      default:
        return JSON.stringify(last.result)
    }
  }
}

/**
 * One job: what it does, when it runs, how the last run went, a way to force it,
 * and — for the two mail jobs — the schedule control itself, so the setting sits
 * on the thing it changes instead of in a separate panel the operator has to
 * mentally connect back to it.
 */
function JobRow({
  job,
  onRan,
  children,
}: {
  readonly job: JobStatus
  readonly onRan: () => void
  readonly children?: React.ReactNode
}) {
  const { t } = useI18n()
  const ago = useAgo()
  const outcome = useOutcome()
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  const trigger = async () => {
    setBusy(true)
    setFailure(null)
    try {
      await runJob(job.name)
      onRan()
    } catch (err) {
      // The call itself failed (offline, session expired). A job that ran and
      // failed comes back as ok:false and is shown in the status line instead.
      setFailure(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const Icon = JOB_ICONS[job.name] ?? ArrowClockwiseIcon
  const last = job.last
  const text = outcome(job)

  return (
    <li className="border-line hover:bg-canvas/60 -mx-4 flex flex-col gap-2 border-b px-4 py-4 transition-colors last:border-b-0">
      <div className="flex items-baseline gap-3">
        <Icon size={15} className="text-ink-faint shrink-0 translate-y-0.5" />

        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-ink text-sm font-medium text-balance">
            {t(`automation.job.${job.name}`)}
          </span>
          {/* `pretty` rather than `balance`: these are one-line explanations, and
              the thing worth avoiding is a single orphaned word on line two. */}
          <span className="text-ink-faint text-xs text-pretty">
            {t(`automation.job.${job.name}.what`)}
          </span>
        </div>

        {/* 36px tall and 40px of touch target with the inline padding — the
            row's only control should not need aiming at. `transition-colors`
            plus a transform on press, never `transition: all`. */}
        <button
          type="button"
          onClick={trigger}
          disabled={busy}
          aria-busy={busy}
          className="border-line text-ink-muted hover:text-ink hover:border-ink-faint focus-visible:ring-accent flex h-9 shrink-0 cursor-pointer items-center gap-2 rounded-lg border px-3.5 text-xs transition-[color,border-color,transform] duration-150 outline-none focus-visible:ring-2 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ArrowClockwiseIcon size={13} className={busy ? 'animate-spin' : undefined} />
          {busy ? t('automation.job.running') : t('automation.job.run')}
        </button>
      </div>

      {/* One status line, indented under the name. It used to be three separate
          health signals per card — a 4px coloured rail, a tinted icon badge and
          this dot — which is two more than the reading needs, and the rail broke
          DESIGN.md's Hairline Rule outright. */}
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 ps-6 text-xs">
        <span className="text-ink-faint">{job.schedule}</span>
        <span aria-hidden className="text-ink-faint">
          ·
        </span>
        {last ? (
          <>
            {/* The outcome as a pill rather than loose coloured text: it is the
                one thing on the row that is scanned down a column, and a shape
                is findable at a glance in a way a tinted sentence is not. The
                dot stays, so the state never rests on hue alone. */}
            <span
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5',
                last.ok
                  ? 'text-status-ok bg-status-ok/10'
                  : 'text-status-fail bg-status-fail/10',
              )}
            >
              <span
                aria-hidden
                className={cn('size-1.5 rounded-full', last.ok ? 'bg-status-ok' : 'bg-status-fail')}
              />
              {t('automation.job.lastRun', { when: ago(last.at) })}
            </span>
            {text && (
              <span className="text-ink-muted min-w-0 flex-1 truncate" title={text}>
                {text}
              </span>
            )}
          </>
        ) : (
          <span className="text-ink-faint">{t('automation.job.never')}</span>
        )}
      </p>

      {children && <div className="ps-6 pt-1">{children}</div>}

      {failure && (
        <p role="alert" className="text-status-fail flex items-start gap-1.5 ps-6 text-xs break-all">
          <WarningCircleIcon size={14} className="mt-px shrink-0" />
          {failure}
        </p>
      )}
    </li>
  )
}

/**
 * A bordered group of rows.
 *
 * DESIGN.md prefers a label plus a rule to a container, and the page still uses
 * that for its top-level sections — but the two mail jobs and the four
 * housekeeping jobs are answers to different questions ("did the manager get
 * their report?" vs "is the plumbing sound?"), and a single flat list of six
 * made the operator re-sort them by eye every visit. One tonal step and a
 * hairline is the cheapest thing that separates them.
 */
function Panel({
  title,
  aside,
  index = 0,
  children,
}: {
  readonly title: string
  /** Small right-aligned figure in the header — a count, a state. */
  readonly aside?: React.ReactNode
  readonly index?: number
  readonly children: React.ReactNode
}) {
  const still = useReducedMotion()
  return (
    <motion.section
      // Staggered by position, so the three panels arrive as a sequence rather
      // than as one flash. 60ms is enough to read as order and short enough
      // that nobody waits for the page.
      initial={still ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20, delay: index * 0.06 }}
      className="border-line bg-surface flex min-w-0 flex-col rounded-xl border"
    >
      <div className="border-line flex items-center gap-3 border-b px-4 py-2.5">
        <h3 className="text-ink-faint text-[0.6875rem] font-medium tracking-wide uppercase">
          {title}
        </h3>
        {aside && <span className="text-ink-faint tabular ms-auto text-[0.6875rem]">{aside}</span>}
      </div>
      <div className="px-4">{children}</div>
    </motion.section>
  )
}

const MAIL_JOBS = ['daily_report', 'weekly_report']

function JobsBand({
  jobs,
  ordered,
  controls,
}: {
  readonly jobs: Async<{ jobs: JobStatus[] }>
  readonly ordered: JobStatus[]
  readonly controls: Record<string, React.ReactNode>
}) {
  const { t } = useI18n()
  if (jobs.error) return <ErrorState message={jobs.error} onRetry={jobs.reload} />
  if (!ordered.length) return <Skeleton className="h-64" />

  const mails = ordered.filter((j) => MAIL_JOBS.includes(j.name))
  const upkeep = ordered.filter((j) => !MAIL_JOBS.includes(j.name))

  // Rows inside each panel, never a grid of bordered cards: identical rounded
  // boxes are the "endless card grid" DESIGN.md names as an anti-pattern, and
  // the Ledger already establishes rows as how this app shows a set of things
  // that differ only by their values.
  const rows = (list: JobStatus[]) => (
    <ul className="flex flex-col">
      {list.map((job) => (
        <JobRow key={job.name} job={job} onRan={jobs.reload}>
          {controls[job.name]}
        </JobRow>
      ))}
    </ul>
  )

  // How many of these ran and came back clean — the header figure that saves
  // reading every row to answer "is the machine healthy?".
  const health = (list: JobStatus[]) => {
    const ran = list.filter((j) => j.last)
    const ok = ran.filter((j) => j.last?.ok).length
    return ran.length === 0 ? t('automation.job.never') : `${ok}/${ran.length}`
  }

  return (
    <div className="flex flex-col gap-4">
      <Panel title={t('automation.plan.title')} index={0}>
        <div className="py-4">
          <DayPlan jobs={ordered} />
        </div>
      </Panel>
      {mails.length > 0 && (
        <Panel title={t('automation.group.mails')} aside={health(mails)} index={1}>
          {rows(mails)}
        </Panel>
      )}
      {upkeep.length > 0 && (
        <Panel title={t('automation.group.upkeep')} aside={health(upkeep)} index={2}>
          {rows(upkeep)}
        </Panel>
      )}
    </div>
  )
}

export function AutomationPage() {
  const { t, locale } = useI18n()
  const stored = useApi('settings', api.settings)
  // 30s: the tightest job runs every 5 min, so anything faster repaints the same row.
  const jobs = useApi('jobs', api.jobs, 30_000)

  const [values, setValues] = useState<EditableSettings>(DEFAULTS)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [newEmail, setNewEmail] = useState('')
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{
    to: string
    ok: boolean
    message?: string
  } | null>(null)

  // Server values win on load; local edits win afterwards until saved.
  useEffect(() => {
    if (stored.data && !dirty) setValues({ ...DEFAULTS, ...stored.data.settings })
  }, [stored.data, dirty])

  const set = <K extends keyof EditableSettings>(key: K, value: EditableSettings[K]) => {
    setValues((v) => ({ ...v, [key]: value }))
    setDirty(true)
    setSaved(false)
  }

  const days = useMemo(() => {
    const fmt = new Intl.DateTimeFormat(intlLocaleOf(locale), { weekday: 'long' })
    // 2026-06-01 is a Monday, so index 0 lands on Monday — same base as the
    // scheduler's `datetime.weekday()`, which is what makes 4 mean Friday in both.
    return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2026, 5, 1 + i)))
  }, [locale])

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      await putSettings(values)
      setDirty(false)
      setSaved(true)
      stored.reload()
      // The schedule labels are rendered by the API from these values.
      jobs.reload()
      window.setTimeout(() => setSaved(false), 2500)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  const addEmail = () => {
    const address = newEmail.trim()
    // Deliberately loose: the Test button is the real validation, not a regex.
    if (!address?.includes('@') || values.emails.includes(address)) return
    set('emails', [...values.emails, address])
    setNewEmail('')
  }

  const test = async (address: string) => {
    setTesting(address)
    setTestResult(null)
    try {
      await sendTestMail(address)
      setTestResult({ to: address, ok: true })
    } catch (err) {
      setTestResult({
        to: address,
        ok: false,
        message: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setTesting(null)
    }
  }

  if (stored.error) return <ErrorState message={stored.error} onRetry={stored.reload} />
  if (stored.loading) return <Skeleton className="mt-8 h-96 rounded-xl" />

  const field =
    'border-line focus:border-accent text-ink bg-canvas rounded-md border px-3 py-2 text-sm outline-none transition-colors'

  // Schedule controls, mounted inside the card of the job they drive.
  const CONTROLS: Record<string, React.ReactNode> = {
    daily_report: (
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="daily-time"
          className="text-ink-faint text-[0.6875rem] tracking-wide uppercase"
        >
          {t('automation.dailyAt')}
        </label>
        <input
          id="daily-time"
          type="time"
          value={values.daily_time}
          onChange={(e) => set('daily_time', e.target.value)}
          className={cn(field, 'tabular w-36')}
        />
      </div>
    ),
    weekly_report: (
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="weekly-day"
            className="text-ink-faint text-[0.6875rem] tracking-wide uppercase"
          >
            {t('automation.weeklyOn')}
          </label>
          <select
            id="weekly-day"
            value={values.weekly_day}
            onChange={(e) => set('weekly_day', Number(e.target.value))}
            className={cn(field, 'capitalize')}
          >
            {days.map((d, i) => (
              <option key={d} value={i}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="weekly-time"
            className="text-ink-faint text-[0.6875rem] tracking-wide uppercase"
          >
            {t('automation.at')}
          </label>
          <input
            id="weekly-time"
            type="time"
            value={values.weekly_time}
            onChange={(e) => set('weekly_time', e.target.value)}
            className={cn(field, 'tabular w-36')}
          />
        </div>
      </div>
    ),
  }

  const ordered = (jobs.data?.jobs ?? [])
    .slice()
    .sort((a, b) => JOB_ORDER.indexOf(a.name) - JOB_ORDER.indexOf(b.name))

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-8 pt-8"
    >
      <p className="text-ink-faint max-w-[70ch] text-sm">{t('automation.intro')}</p>

      <Band title={t('automation.jobs')} hint={t('automation.jobsHint')}>
        <JobsBand jobs={jobs} ordered={ordered} controls={CONTROLS} />
      </Band>

      <Band
        title={t('automation.recipients')}
        hint={t('automation.recipientsHint')}
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex min-w-64 flex-1 flex-col gap-1.5">
              <label
                htmlFor="new-email"
                className="text-ink-faint text-[0.6875rem] tracking-wide uppercase"
              >
                {t('automation.addEmail')}
              </label>
              <input
                id="new-email"
                type="email"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addEmail()
                  }
                }}
                placeholder="directeur@aznet.ma"
                className={cn(field, 'placeholder:text-ink-faint')}
              />
            </div>
            <button
              type="button"
              onClick={addEmail}
              disabled={!newEmail.trim() || !newEmail.includes('@')}
              className={cn(
                'flex items-center gap-2 rounded-md px-3.5 py-2 text-sm transition-transform active:translate-y-px',
                !newEmail.trim() || !newEmail.includes('@')
                  ? 'border-line text-ink-faint cursor-not-allowed border'
                  : 'bg-accent text-white',
              )}
            >
              <PlusIcon size={14} weight="bold" />
              {t('access.add')}
            </button>
          </div>

          {values.emails.length === 0 ? (
            /* A red sentence, not the neutral empty state: an automation with
               no recipients runs every night and reaches nobody, which is a
               fault the page has to look like it is reporting. */
            <p className="text-status-fail flex items-start gap-2 text-sm">
              <WarningCircleIcon size={16} weight="fill" className="mt-px shrink-0" />
              {t('automation.noEmails')}
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {values.emails.map((address) => {
                const result = testResult?.to === address ? testResult : null
                return (
                  <li
                    key={address}
                    className="border-line bg-surface flex flex-wrap items-center gap-3 rounded-md border px-3 py-2.5"
                  >
                    {/* The initial stands in for an avatar the app does not have
                        and should not invent — it makes a list of addresses
                        scannable by shape instead of by reading each one. */}
                    <span className="border-line text-ink-muted flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-medium uppercase">
                      {address.trim().charAt(0) || '@'}
                    </span>

                    <span className="text-ink min-w-0 flex-1 truncate text-sm">{address}</span>

                    {result && (
                      <span
                        className={cn(
                          'flex items-center gap-1.5 text-xs',
                          result.ok ? 'text-status-ok' : 'text-status-fail',
                        )}
                      >
                        {result.ok ? (
                          <CheckIcon size={13} weight="bold" />
                        ) : (
                          <WarningCircleIcon size={13} weight="fill" />
                        )}
                        {result.ok ? t('automation.testSent') : t('automation.testFailed')}
                      </span>
                    )}

                    <button
                      type="button"
                      onClick={() => test(address)}
                      disabled={testing === address}
                      className="border-line text-ink-muted hover:text-ink flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors active:translate-y-px disabled:opacity-50"
                    >
                      <PaperPlaneTiltIcon size={13} />
                      {testing === address ? t('automation.testing') : t('automation.test')}
                    </button>

                    <button
                      type="button"
                      onClick={() =>
                        set(
                          'emails',
                          values.emails.filter((e) => e !== address),
                        )
                      }
                      aria-label={`${t('access.remove')} ${address}`}
                      className="text-ink-faint hover:text-status-fail transition-colors"
                    >
                      <TrashIcon size={15} />
                    </button>
                  </li>
                )
              })}
            </ul>
          )}

          {/* The API names the missing env vars verbatim on a 422. */}
          {testResult?.ok === false && testResult.message && (
            <p className="text-status-fail max-w-[70ch] text-xs break-all">{testResult.message}</p>
          )}
        </div>
      </Band>

      {error && <ErrorState message={error} onRetry={save} />}

      {/*
        Sticky rather than at the end of the page: the schedule controls now live
        inside job cards further up, and a save button below the fold means an
        edited time silently not being saved.
      */}
      <div className="bg-canvas border-line sticky bottom-0 flex items-center gap-4 border-t py-4">
        <button
          type="button"
          onClick={save}
          disabled={!dirty || saving}
          className={cn(
            'rounded-md px-4 py-2 text-sm transition-transform active:translate-y-px',
            !dirty || saving
              ? 'border-line text-ink-faint cursor-not-allowed border'
              : 'bg-accent text-white',
          )}
        >
          {saving ? t('inbox.saving') : t('inbox.save')}
        </button>
        {saved && (
          <span className="text-status-ok flex items-center gap-1.5 text-xs">
            <CheckIcon size={13} weight="bold" />
            {t('inbox.saved')}
          </span>
        )}
        {dirty && !saving && (
          <span className="text-ink-faint text-xs">{t('automation.unsaved')}</span>
        )}
        <p className="text-ink-faint ms-auto max-w-[46ch] text-end text-xs">
          {t('automation.enforceNote')}
        </p>
      </div>
    </motion.div>
  )
}
