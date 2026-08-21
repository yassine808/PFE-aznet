import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import {
  ArrowClockwiseIcon,
  BellRingingIcon,
  BroomIcon,
  CalendarBlankIcon,
  CheckIcon,
  ClockCountdownIcon,
  EnvelopeSimpleIcon,
  PaperPlaneTiltIcon,
  PauseIcon,
  PlayIcon,
  PlusIcon,
  TrashIcon,
  UserFocusIcon,
  WarningCircleIcon,
} from '@phosphor-icons/react'
import {
  api,
  BASE,
  putSettings,
  runJob,
  sendTestMail,
  useApi,
  type Async,
  type AppSettings,
  type JobStatus,
} from '@/lib/api'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

// The four fields this form edits. `stt_chain` is deliberately absent even
// though AppSettings has it: the save PUTs this whole object, and the director
//'s live STT order lives in a different panel — a whole-object save here must
// not reset it to a default it never chose.
// `paused_jobs` is excluded for the same reason `stt_chain` is: this form PUTs
// its whole object, and a save carrying a stale list would silently undo a
// pause the operator set on a row seconds earlier. It is written by the row's
// own switch, one key at a time.
type EditableSettings = Required<Omit<AppSettings, 'stt_chain' | 'paused_jobs' | 'job_schedules'>>
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
const JOB_ORDER = [
  'daily_report',
  'weekly_report',
  'reminders',
  'sheet_queue',
  'profiles',
  'prune_logs',
]

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
            .map((job) => {
              const name = t(`automation.job.${job.name}`)
              return `${name} — ${job.schedule}`
            })
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
                {String(Math.floor(at / 60)).padStart(2, '0')}:{String(at % 60).padStart(2, '0')}
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
          due: n('due'),
          notified: n('notified'),
          emailed: n('emailed'),
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
  pause,
  children,
}: {
  readonly job: JobStatus
  readonly onRan: () => void
  /** This job's own pause switch, rendered beside its Run button. */
  readonly pause?: React.ReactNode
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
  const what = t(`automation.job.${job.name}.what`)
  const jobLabel = t(`automation.job.${job.name}`)

  return (
    /*
      One line per job.

      Each row used to be a two-line description plus a status line plus, for
      the two mail jobs, a schedule form — around 110px each, so six jobs alone
      filled a screen and the recipient list was permanently below the fold.
      The explanation is a `title`, not a second line: it answers a question
      asked once, when you first meet the job, and then costs a line forever.
      What is read every visit — when it runs, whether it worked, and the way
      to run it now — stays on the surface.
    */
    <li className="border-line hover:bg-canvas/60 flex flex-col border-b transition-colors last:border-b-0">
      {/* Name over schedule, not name beside schedule. In one column there was
          room for both on a line; in half of one the sentence squeezed the
          controls until the time field clipped its own value. The second line
          costs nothing — the row is already taller than one line of text
          because of the controls — and the name is what the eye lands on
          first either way. */}
      <div className="flex items-center gap-2.5 py-2">
        <Icon size={15} className="text-ink-faint shrink-0" />

        <span className="flex min-w-0 flex-1 flex-col">
          <span className="text-ink truncate text-sm leading-tight" title={what}>
            {jobLabel}
          </span>
          <span
            className={cn(
              'truncate text-[0.6875rem] leading-tight',
              job.paused ? 'text-status-warn' : 'text-ink-faint',
            )}
          >
            {job.paused ? t('automation.pausedNote') : job.schedule}
          </span>
        </span>

        {/* The outcome as a pill: it is the one thing scanned down a column, and
            a shape is findable at a glance in a way a tinted sentence is not.
            The dot stays, so the state never rests on hue alone. The run's own
            output is the pill's tooltip rather than a fourth line of text. */}
        {last ? (
          <span
            title={text ?? undefined}
            className={cn(
              'inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[0.6875rem]',
              last.ok ? 'text-status-ok bg-status-ok/10' : 'text-status-fail bg-status-fail/10',
            )}
          >
            <span
              aria-hidden
              className={cn('size-1.5 rounded-full', last.ok ? 'bg-status-ok' : 'bg-status-fail')}
            />
            {ago(last.at)}
          </span>
        ) : (
          <span className="text-ink-faint shrink-0 text-[0.6875rem]">—</span>
        )}

        {pause}

        {/* Icon-only: the label was the widest thing on the row and said the
            same thing six times. 32px with the padding, still a real target. */}
        <button
          type="button"
          onClick={trigger}
          disabled={busy}
          aria-busy={busy}
          title={t('automation.job.run')}
          aria-label={`${t('automation.job.run')} — ${jobLabel}`}
          className="border-line text-ink-muted hover:text-ink hover:border-ink-faint focus-visible:ring-accent flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border transition-[color,border-color,transform] duration-150 outline-none focus-visible:ring-2 active:scale-[0.94] disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ArrowClockwiseIcon size={14} className={busy ? 'animate-spin' : undefined} />
        </button>
      </div>

      {children}

      {failure && (
        <p
          role="alert"
          className="text-status-fail flex items-start gap-1.5 pb-2 text-xs break-all"
        >
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

const MAIL_JOBS = new Set(['daily_report', 'weekly_report'])

/**
 * One job's own schedule, edited on its own row.
 *
 * There was a single "Entretien à 03:00" on the upkeep band header, which is
 * the wrong shape twice over: it governed two of the seven jobs in that band
 * and said nothing about the other five, and it put a control somewhere other
 * than on the thing it controls. Every row now carries its own.
 *
 * The control follows the job's kind because the two kinds answer different
 * questions. A job that runs at a moment gets a clock; a job that repeats gets
 * a number of minutes. "At what time should the retry queue drain?" has no
 * answer, and "how often should the daily report be sent?" has a misleading
 * one.
 *
 * Writes on commit rather than joining the settings form: that form PUTs its
 * whole object, so a Save carrying a stale schedule would undo an edit made
 * here seconds earlier.
 */
function JobSchedule({
  job,
  schedules,
  onChanged,
}: {
  readonly job: JobStatus
  readonly schedules: Record<string, string | number>
  readonly onChanged: () => void
}) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const interval = job.kind === 'interval'
  const jobLabel = t(`automation.job.${job.name}`)

  const save = async (raw: string) => {
    const next: string | number = interval ? Number(raw) : raw
    if (raw === '' || (interval && (!Number.isFinite(next as number) || (next as number) < 1))) {
      // Refused rather than stored: a zero interval makes the job due on every
      // 30 s tick, and for the message retry that means hammering a provider
      // that is already failing.
      setFailed(true)
      return
    }
    setBusy(true)
    setFailed(false)
    try {
      await putSettings({ job_schedules: { ...schedules, [job.name]: next } })
      onChanged()
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="flex shrink-0 items-center gap-1">
      <input
        type={interval ? 'number' : 'time'}
        min={interval ? 1 : undefined}
        step={interval ? 1 : undefined}
        defaultValue={interval ? (job.every_minutes ?? '') : (job.at ?? '')}
        disabled={busy}
        aria-label={`${jobLabel} — ${interval ? t('automation.everyMinutes') : t('automation.runsAt')}`}
        // On blur, not on change: a time input fires as the hour digit is typed,
        // which would store "0:00" on the way to "04:30".
        onBlur={(e) => void save(e.target.value)}
        className={cn(
          'border-line bg-canvas text-ink tabular focus:border-accent rounded-md border px-2 py-1 text-xs outline-none transition-colors disabled:opacity-50',
          // A 12-hour locale renders `18:30` as `06:30 PM`, and w-24 clipped
          // the marker: the field showed "06:30 P" beside a label reading
          // 18:30, which reads as two different times for one setting.
          interval ? 'w-16' : 'w-[7.5rem]',
          failed && 'border-status-fail',
        )}
      />
      {interval && <span className="text-ink-faint text-[0.625rem]">{t('automation.min')}</span>}
    </span>
  )
}

/**
 * Pause or resume one band of the scheduler.
 *
 * Writes immediately instead of joining the settings form: this is a switch,
 * not a field. An operator pausing the nightly band because they are about to
 * work on the Sheet should not then have to find a Save button — and the form
 * beside it may hold half-typed edits that must not be committed as a side
 * effect of flipping a switch. `put_settings` upserts only the keys it is
 * given, so sending this one key touches nothing else.
 */
function PauseToggle({
  name,
  paused,
  pausedList,
  onChanged,
}: {
  readonly name: string
  readonly paused: boolean
  /** The whole list as the server last reported it. Sent back with one name
   *  added or removed, because the setting is the list — writing a single
   *  boolean would need one key per job and a migration every time a job is
   *  added, and nine of them arrived this month. */
  readonly pausedList: readonly string[]
  readonly onChanged: () => void
}) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)

  const toggle = async () => {
    setBusy(true)
    setError(false)
    try {
      const next = paused
        ? pausedList.filter((n) => n !== name)
        : [...new Set([...pausedList, name])]
      await putSettings({ paused_jobs: next })
      onChanged()
    } catch {
      // Left visible rather than thrown away: a pause that silently failed
      // would show "running" while the operator believes it is stopped.
      setError(true)
    } finally {
      setBusy(false)
    }
  }

  let pauseLabelKey = 'automation.pause'
  if (error) pauseLabelKey = 'automation.pauseFailed'
  else if (paused) pauseLabelKey = 'automation.resume'

  return (
    <button
      type="button"
      disabled={busy}
      onClick={toggle}
      aria-pressed={paused}
      title={paused ? t('automation.resumeHint') : t('automation.pauseHint')}
      className={cn(
        'focus-visible:ring-accent inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-md border px-2.5 text-[0.6875rem] font-medium transition-colors outline-none focus-visible:ring-2 active:translate-y-px disabled:opacity-40',
        paused
          ? 'border-status-warn/40 text-status-warn'
          : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
      )}
    >
      {paused ? <PlayIcon size={12} weight="fill" /> : <PauseIcon size={12} weight="fill" />}
      {t(pauseLabelKey)}
    </button>
  )
}

function JobsBand({
  jobs,
  ordered,
  controls,
  onChanged,
  pausedList,
  schedules,
  delivery,
}: {
  readonly onChanged: () => void
  readonly pausedList: readonly string[]
  readonly schedules: Record<string, string | number>
  /** When the weekly report goes out and who receives it — rendered under the
   *  report rows, because it is the same subject as the rows above it. */
  readonly delivery?: React.ReactNode
  readonly jobs: Async<{ jobs: JobStatus[] }>
  readonly ordered: JobStatus[]
  readonly controls: Record<string, React.ReactNode>
}) {
  const { t } = useI18n()
  if (jobs.error) return <ErrorState message={jobs.error} onRetry={jobs.reload} />
  // An empty list and a list still in flight are two different facts. Keying the
  // skeleton on "no rows" made a scheduler with nothing registered pulse
  // forever, which reads as a page that never finished loading.
  if (jobs.loading && !jobs.data) return <Skeleton className="h-64" />
  if (!ordered.length) return <EmptyState icon={ClockCountdownIcon} body={t('automation.noJobs')} />

  const mails = ordered.filter((j) => MAIL_JOBS.has(j.name))
  const upkeep = ordered.filter((j) => !MAIL_JOBS.has(j.name))

  // Rows inside each panel, never a grid of bordered cards: identical rounded
  // boxes are the "endless card grid" DESIGN.md names as an anti-pattern, and
  // the Ledger already establishes rows as how this app shows a set of things
  // that differ only by their values.
  const rows = (list: JobStatus[]) => (
    <ul className="flex flex-col">
      {list.map((job) => (
        <JobRow
          key={job.name}
          job={job}
          onRan={jobs.reload}
          pause={
            <>
              {/* A job whose timing is not a preference shows none: the watch
                  that notices a shortage is only useful if it runs often, and
                  offering a control implies a choice that does not exist. */}
              {job.editable !== false && (
                <JobSchedule job={job} schedules={schedules} onChanged={onChanged} />
              )}
              <PauseToggle
                name={job.name}
                paused={Boolean(job.paused)}
                pausedList={pausedList}
                onChanged={onChanged}
              />
            </>
          }
        >
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
        <div className="py-3">
          <DayPlan jobs={ordered} />
        </div>
      </Panel>
      {/* Side by side from xl, upkeep first. Stacked, the two bands ran to about
          two screens and the recipient list sat permanently below the fold — the
          page asked you to scroll to answer "who gets the report?".
          `items-start` so the shorter column stops at its own content instead of
          stretching to match the taller one, which would draw a panel border
          around a block of empty space. */}
      <div className="grid min-w-0 items-start gap-4 xl:grid-cols-2">
        {upkeep.length > 0 && (
          <Panel title={t('automation.group.upkeep')} aside={health(upkeep)} index={1}>
            {rows(upkeep)}
          </Panel>
        )}
        {mails.length > 0 && (
          <Panel title={t('automation.sending')} aside={health(mails)} index={2}>
            {rows(mails)}
            {delivery}
          </Panel>
        )}
      </div>
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

  // Server values win on load; local edits win afterwards until saved. Keyed on
  // the data alone — not on `dirty` — so the `dirty: false` transition right
  // after a successful save cannot re-apply the *stale* copy the reload is
  // still replacing: the form would snap back to the old time for a moment,
  // mid-typing if the operator had already started the next edit. `dirty` is
  // still checked at arrival time — an edit in flight always keeps the form.
  useEffect(() => {
    if (stored.data && !dirty) setValues({ ...DEFAULTS, ...stored.data.settings })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stored.data])

  const set = <K extends keyof EditableSettings>(key: K, value: EditableSettings[K]) => {
    setValues((v) => ({ ...v, [key]: value }))
    setDirty(true)
    setSaved(false)
  }

  // Straight off the server's copy, never mirrored into form state: the pause
  // switches write one key at a time and this page's Save PUTs a whole object,
  // so a mirrored copy would let a Save undo a pause set seconds earlier.
  const pausedJobs = useMemo<string[]>(() => {
    const raw = (stored.data?.settings as { paused_jobs?: unknown })?.paused_jobs
    if (Array.isArray(raw)) return raw.map(String)
    if (typeof raw === 'string')
      return raw
        .split(',')
        .map((v) => v.trim())
        .filter(Boolean)
    return []
  }, [stored.data])

  const jobSchedules = useMemo<Record<string, string | number>>(() => {
    const raw = (stored.data?.settings as { job_schedules?: unknown })?.job_schedules
    return raw && typeof raw === 'object' && !Array.isArray(raw)
      ? (raw as Record<string, string | number>)
      : {}
  }, [stored.data])

  const days = useMemo(() => {
    const fmt = new Intl.DateTimeFormat(intlLocaleOf(locale), { weekday: 'long' })
    // 2026-06-01 is a Monday, so index 0 lands on Monday — same base as the
    // scheduler's `datetime.weekday()`, which is what makes 4 mean Friday in both.
    return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2026, 5, 1 + i)))
  }, [locale])

  const save = useCallback(async () => {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values])

  /**
   * Save on its own, shortly after the last edit.
   *
   * The Save button was the last place on this page where a change did not
   * take: the pause switches and the per-job schedules already write
   * themselves, so an operator who changed the weekday and walked away left it
   * unsaved next to two controls that had saved instantly. One page, two
   * rules, and the inconsistent one silently loses the edit.
   *
   * Debounced rather than fired per keystroke: typing an address would
   * otherwise PUT once per character. 900 ms is long enough to finish a word
   * and short enough that nobody navigates away inside it — and `pagehide`
   * below closes even that gap.
   */
  useEffect(() => {
    if (!dirty || saving) return
    const timer = window.setTimeout(() => void save(), 900)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values, dirty])

  /**
   * The last edit, when the tab is closing.
   *
   * `pagehide` and not `beforeunload`: the latter is unreliable on mobile and
   * asks the browser to prompt. `sendBeacon` because a normal fetch is
   * cancelled the moment the document goes away — the same reason the page
   * timer in App.tsx uses it.
   */
  useEffect(() => {
    const flush = () => {
      if (!dirty) return
      navigator.sendBeacon?.(
        `${BASE}/settings`,
        new Blob([JSON.stringify({ values })], { type: 'application/json' }),
      )
    }
    window.addEventListener('pagehide', flush)
    return () => window.removeEventListener('pagehide', flush)
  }, [dirty, values])

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

  const CONTROLS: Record<string, React.ReactNode> = {}

  /* Everything about sending a report that is not a time on a row: which day
     the weekly one goes out, and who receives both. It is rendered inside the
     reports band rather than beside it, so one panel answers when, to whom,
     and how the last run went. */
  const DELIVERY = (
    <div className="flex flex-col gap-3 py-3">
      {/* The weekday is the one scheduling fact a time input cannot
                  express, so it stays — beside the recipients whose cadence it
                  decides, separated by a rule rather than boxed. */}
      <div className="border-line/70 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b pb-3">
        <label
          htmlFor="weekly-day"
          className="text-ink-muted flex min-w-0 flex-col gap-0.5 text-xs"
        >
          {t('automation.weeklyOn')}
          <span className="text-ink-faint text-[0.625rem]">{t('automation.timesOnRows')}</span>
        </label>
        <select
          id="weekly-day"
          value={values.weekly_day}
          onChange={(e) => set('weekly_day', Number(e.target.value))}
          className={cn(field, 'w-40 capitalize')}
        >
          {days.map((d, i) => (
            <option key={d} value={i}>
              {d}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-2">
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
          aria-label={t('automation.addEmail')}
          className={cn(field, 'placeholder:text-ink-faint min-w-0 flex-1')}
        />
        <button
          type="button"
          onClick={addEmail}
          disabled={!newEmail.trim() || !newEmail.includes('@')}
          title={t('access.add')}
          aria-label={t('access.add')}
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-md transition-transform active:translate-y-px',
            !newEmail.trim() || !newEmail.includes('@')
              ? 'border-line text-ink-faint cursor-not-allowed border'
              : 'bg-accent cursor-pointer text-white',
          )}
        >
          <PlusIcon size={15} weight="bold" />
        </button>
      </div>

      {values.emails.length === 0 ? (
        /* A red sentence, not the neutral empty state: an automation
                   with no recipients runs every night and reaches nobody, which
                   is a fault the page has to look like it is reporting. */
        <p className="text-status-fail flex items-start gap-2 text-xs">
          <WarningCircleIcon size={15} weight="fill" className="mt-px shrink-0" />
          {t('automation.noEmails')}
        </p>
      ) : (
        /* Rows, not bordered cards, and both controls are icons: the
                   list is short, every entry is the same shape, and the
                   addresses are the only thing worth reading in it. */
        <ul className="flex flex-col">
          {values.emails.map((address) => {
            const result = testResult?.to === address ? testResult : null
            return (
              <li
                key={address}
                className="border-line flex items-center gap-2 border-b py-1.5 last:border-b-0"
              >
                <span className="text-ink min-w-0 flex-1 truncate text-sm">{address}</span>

                {result && (
                  <span
                    title={result.ok ? t('automation.testSent') : t('automation.testFailed')}
                    className={cn('shrink-0', result.ok ? 'text-status-ok' : 'text-status-fail')}
                  >
                    {result.ok ? (
                      <CheckIcon size={14} weight="bold" />
                    ) : (
                      <WarningCircleIcon size={14} weight="fill" />
                    )}
                    <span className="sr-only">
                      {result.ok ? t('automation.testSent') : t('automation.testFailed')}
                    </span>
                  </span>
                )}

                <button
                  type="button"
                  onClick={() => test(address)}
                  disabled={testing === address}
                  title={testing === address ? t('automation.testing') : t('automation.test')}
                  aria-label={`${t('automation.test')} ${address}`}
                  className="border-line text-ink-muted hover:text-ink flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md border transition-colors active:translate-y-px disabled:opacity-50"
                >
                  <PaperPlaneTiltIcon size={12} />
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
                  className="text-ink-faint hover:text-status-fail shrink-0 cursor-pointer transition-colors"
                >
                  <TrashIcon size={14} />
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {/* The API names the missing env vars verbatim on a 422. */}
      {testResult?.ok === false && testResult.message && (
        <p className="text-status-fail text-xs break-all">{testResult.message}</p>
      )}

      <p className="text-ink-faint text-[0.6875rem]">{t('automation.recipientsHint')}</p>
    </div>
  )

  const ordered = (jobs.data?.jobs ?? [])
    .slice()
    .sort((a, b) => JOB_ORDER.indexOf(a.name) - JOB_ORDER.indexOf(b.name))

  let saveStatus = <span className="text-ink-faint">{t('automation.autoSaveNote')}</span>
  if (saving) {
    saveStatus = (
      <span className="text-ink-muted flex items-center gap-1.5">
        <ArrowClockwiseIcon size={13} className="animate-spin" />
        {t('inbox.saving')}
      </span>
    )
  } else if (saved) {
    saveStatus = (
      <span className="text-status-ok flex items-center gap-1.5">
        <CheckIcon size={13} weight="bold" />
        {t('automation.savedAuto')}
      </span>
    )
  } else if (dirty) {
    saveStatus = <span className="text-ink-faint">{t('automation.savingSoon')}</span>
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-5 pt-6"
    >
      {/*
        Two columns from `xl` up.

        The page was one stack: intro paragraph, timeline, six tall job rows,
        then the recipient list — so the two halves of the same question ("what
        runs" and "where does it go") were a screen and a half apart, and
        checking whether tonight's mail had a recipient meant scrolling past
        every housekeeping job. They are side by side now, and the whole page
        fits one screen at 1440.
      */}
      {/* One column. The right-hand column held exactly one panel — when the
          reports go out and to whom — and that belongs to the reports band
          itself, not beside it. Two columns existed to separate "status" from
          "settings", a split this page stopped having the moment every row
          started carrying its own controls. */}
      <div className="flex min-w-0 flex-col gap-5">
        <JobsBand
          jobs={jobs}
          ordered={ordered}
          controls={CONTROLS}
          onChanged={() => {
            jobs.reload()
            stored.reload()
          }}
          pausedList={pausedJobs}
          schedules={jobSchedules}
          delivery={DELIVERY}
        />
      </div>

      {error && <ErrorState message={error} onRetry={save} />}

      {/*
        A status line, not a button. Everything on this page saves itself now,
        so the bar's job is to say which of the three states the form is in —
        and to keep saying it in the same place, because a message that moves is
        a message that gets missed. Sticky for the same reason it always was:
        an edit made at the top must not report its outcome below the fold.
      */}
      <div className="bg-canvas border-line sticky bottom-0 flex items-center gap-3 border-t py-4">
        <span
          // Polite, not assertive: this narrates a background save, and a
          // screen reader should finish the sentence it is on first.
          aria-live="polite"
          className="flex min-h-5 items-center gap-1.5 text-xs"
        >
          {saveStatus}
        </span>
        <p className="text-ink-faint ms-auto max-w-[46ch] text-end text-xs">
          {t('automation.enforceNote')}
        </p>
      </div>
    </motion.div>
  )
}
