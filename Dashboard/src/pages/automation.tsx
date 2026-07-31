import { useEffect, useMemo, useState } from 'react'
import { motion } from 'motion/react'
import {
  ArrowClockwiseIcon,
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
import { FORMATS, type ReportFormat } from '@/lib/report-export'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

const DEFAULTS: Required<AppSettings> = {
  daily_time: '18:30',
  weekly_day: 4,
  weekly_time: '17:00',
  emails: [],
  report_format: 'markdown',
}

// Icon per job, so the four cards are told apart at a glance rather than read.
const JOB_ICONS: Record<string, typeof BroomIcon> = {
  sheet_queue: ArrowClockwiseIcon,
  prune_logs: BroomIcon,
  profiles: UserFocusIcon,
  daily_report: EnvelopeSimpleIcon,
  weekly_report: CalendarBlankIcon,
}

// Order shown to the operator: the two mails they care about first, plumbing last.
const JOB_ORDER = ['daily_report', 'weekly_report', 'sheet_queue', 'profiles', 'prune_logs']

const FORMAT_EXT: Record<ReportFormat, string> = { txt: '.txt', markdown: '.md', docx: '.docx' }

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
function JobCard({
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
    <li className="border-line bg-canvas flex flex-col gap-3 rounded-xl border p-4">
      <div className="flex items-start gap-3">
        <span className="border-line text-ink-muted mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border">
          <Icon size={16} />
        </span>

        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-ink text-sm font-medium">{t(`automation.job.${job.name}`)}</span>
          <span className="text-ink-faint text-xs">{t(`automation.job.${job.name}.what`)}</span>
        </div>

        <button
          type="button"
          onClick={trigger}
          disabled={busy}
          className="border-line text-ink-muted hover:text-ink hover:border-ink-faint flex shrink-0 items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors active:translate-y-px disabled:opacity-50"
        >
          <ArrowClockwiseIcon size={13} className={busy ? 'animate-spin' : undefined} />
          {busy ? t('automation.job.running') : t('automation.job.run')}
        </button>
      </div>

      {children && <div className="ps-11">{children}</div>}

      <div className="border-line flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-3 ps-11 text-xs">
        <span className="text-ink-faint">{job.schedule}</span>
        <span className="text-ink-faint">·</span>
        {last ? (
          <>
            <span
              className={cn(
                'inline-flex items-center gap-1.5',
                last.ok ? 'text-status-ok' : 'text-status-fail',
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
      </div>

      {failure && (
        <p className="text-status-fail flex items-start gap-1.5 ps-11 text-xs break-all">
          <WarningCircleIcon size={14} className="mt-px shrink-0" />
          {failure}
        </p>
      )}
    </li>
  )
}

function JobsBand({
  jobs,
  ordered,
  controls,
}: {
  readonly jobs: Async<{ jobs: JobStatus[] }>
  readonly ordered: JobStatus[]
  readonly controls: Record<string, React.ReactNode>
}) {
  if (jobs.error) return <ErrorState message={jobs.error} onRetry={jobs.reload} />
  if (!ordered.length) return <Skeleton className="h-64 rounded-xl" />
  return (
    <ul className="grid gap-3 lg:grid-cols-2">
      {ordered.map((job) => (
        <JobCard key={job.name} job={job} onRan={jobs.reload}>
          {controls[job.name]}
        </JobCard>
      ))}
    </ul>
  )
}

export function AutomationPage() {
  const { t, locale } = useI18n()
  const stored = useApi('settings', api.settings)
  // 30s: the tightest job runs every 5 min, so anything faster repaints the same row.
  const jobs = useApi('jobs', api.jobs, 30_000)

  const [values, setValues] = useState<Required<AppSettings>>(DEFAULTS)
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

  const set = <K extends keyof Required<AppSettings>>(key: K, value: Required<AppSettings>[K]) => {
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
    if (!address || !address.includes('@') || values.emails.includes(address)) return
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

      <Band title={t('automation.recipients')} hint={t('automation.recipientsHint')}>
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
            <p className="text-status-fail text-sm">{t('automation.noEmails')}</p>
          ) : (
            <ul className="divide-line flex flex-col divide-y">
              {values.emails.map((address) => (
                <li key={address} className="flex flex-wrap items-center gap-3 py-2.5">
                  <span className="text-ink min-w-0 flex-1 truncate text-sm">{address}</span>

                  {testResult?.to === address && (
                    <span
                      className={cn(
                        'text-xs',
                        testResult.ok ? 'text-status-ok' : 'text-status-fail',
                      )}
                    >
                      {testResult.ok ? t('automation.testSent') : t('automation.testFailed')}
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
              ))}
            </ul>
          )}

          {/* The API names the missing env vars verbatim on a 422. */}
          {testResult?.ok === false && testResult.message && (
            <p className="text-status-fail max-w-[70ch] text-xs break-all">{testResult.message}</p>
          )}
        </div>
      </Band>

      <Band title={t('automation.format')} hint={t('automation.formatHint')}>
        <fieldset className="border-line m-0 flex w-fit rounded-md border p-0.5">
          <legend className="sr-only">{t('automation.format')}</legend>
          {FORMATS.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => set('report_format', f)}
              aria-pressed={values.report_format === f}
              className={cn(
                'rounded px-3 py-1.5 text-xs transition-colors active:translate-y-px',
                values.report_format === (f as ReportFormat)
                  ? 'bg-slate-100 text-ink dark:bg-slate-850'
                  : 'text-ink-faint hover:text-ink',
              )}
            >
              {FORMAT_EXT[f]}
            </button>
          ))}
        </fieldset>
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
