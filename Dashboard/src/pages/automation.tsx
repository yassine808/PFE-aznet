import { useEffect, useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { CheckIcon, PaperPlaneTiltIcon, PlusIcon, TrashIcon } from '@phosphor-icons/react'
import { api, putSettings, sendTestMail, useApi, type AppSettings } from '@/lib/api'
import { FORMATS, type ReportFormat } from '@/lib/report-export'
import { useI18n } from '@/lib/i18n'
import { ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

const DEFAULTS: Required<AppSettings> = {
  daily_time: '18:30',
  weekly_day: 5,
  weekly_time: '17:00',
  emails: [],
  report_format: 'markdown',
}

function Band({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col gap-4">
      <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
        {title}
      </h2>
      {children}
    </section>
  )
}

export function AutomationPage() {
  const { t, locale } = useI18n()
  const stored = useApi('settings', api.settings)

  const [values, setValues] = useState<Required<AppSettings>>(DEFAULTS)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [newEmail, setNewEmail] = useState('')
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ to: string; ok: boolean; message?: string } | null>(null)

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
    const fmt = new Intl.DateTimeFormat(locale === 'ar' ? 'ar-MA' : locale === 'en' ? 'en-GB' : 'fr-FR', {
      weekday: 'long',
    })
    // 2026-06-01 is a Monday, so index 0 lands on Monday.
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
      setTestResult({ to: address, ok: false, message: err instanceof Error ? err.message : String(err) })
    } finally {
      setTesting(null)
    }
  }

  if (stored.error) return <ErrorState message={stored.error} onRetry={stored.reload} />
  if (stored.loading) return <Skeleton className="mt-8 h-96 rounded-xl" />

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-8 pt-8"
    >
      <p className="text-ink-faint max-w-[70ch] text-sm">{t('automation.intro')}</p>

      <div className="grid gap-x-10 gap-y-8 lg:grid-cols-2">
        <Band title={t('automation.schedule')}>
          <div className="flex flex-col gap-5">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="daily-time" className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
                {t('automation.dailyAt')}
              </label>
              <input
                id="daily-time"
                type="time"
                value={values.daily_time}
                onChange={(e) => set('daily_time', e.target.value)}
                className="border-line focus:border-accent text-ink bg-canvas tabular w-36 rounded-md border px-3 py-2 text-sm outline-none transition-colors"
              />
            </div>

            <div className="flex flex-wrap items-end gap-4">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="weekly-day" className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
                  {t('automation.weeklyOn')}
                </label>
                <select
                  id="weekly-day"
                  value={values.weekly_day}
                  onChange={(e) => set('weekly_day', Number(e.target.value))}
                  className="border-line focus:border-accent text-ink bg-canvas rounded-md border px-3 py-2 text-sm capitalize outline-none transition-colors"
                >
                  {days.map((d, i) => (
                    <option key={d} value={i}>
                      {d}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="weekly-time" className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
                  {t('automation.at')}
                </label>
                <input
                  id="weekly-time"
                  type="time"
                  value={values.weekly_time}
                  onChange={(e) => set('weekly_time', e.target.value)}
                  className="border-line focus:border-accent text-ink bg-canvas tabular w-36 rounded-md border px-3 py-2 text-sm outline-none transition-colors"
                />
              </div>
            </div>

            {/*
              Read-only on purpose. The 03:00 schedule lives in the n8n workflow,
              not in app_settings — making it editable here would show a time the
              cron does not actually use, which is worse than showing nothing.
            */}
            <div className="border-line flex flex-col gap-1 border-t pt-4">
              <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
                {t('automation.profiles')}
              </span>
              <span className="text-ink tabular text-sm">03:00</span>
              <p className="text-ink-faint max-w-[45ch] text-xs">{t('automation.profilesHint')}</p>
            </div>
          </div>
        </Band>

        <Band title={t('automation.format')}>
          <div className="flex flex-col gap-3">
            <div className="border-line flex w-fit rounded-md border p-0.5" role="group">
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
                  {f === 'txt' ? '.txt' : f === 'markdown' ? '.md' : '.docx'}
                </button>
              ))}
            </div>
            <p className="text-ink-faint max-w-[60ch] text-xs">{t('automation.formatHint')}</p>
          </div>
        </Band>
      </div>

      <Band title={t('automation.recipients')}>
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex min-w-64 flex-1 flex-col gap-1.5">
              <label htmlFor="new-email" className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
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
                className="border-line focus:border-accent text-ink bg-canvas placeholder:text-ink-faint rounded-md border px-3 py-2 text-sm outline-none transition-colors"
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
            <p className="text-ink-faint text-sm">{t('automation.noEmails')}</p>
          ) : (
            <ul className="divide-line flex flex-col divide-y">
              {values.emails.map((address) => (
                <li key={address} className="flex flex-wrap items-center gap-3 py-2.5">
                  <span className="text-ink min-w-0 flex-1 truncate text-sm">{address}</span>

                  {testResult?.to === address && (
                    <span className={cn('text-xs', testResult.ok ? 'text-status-ok' : 'text-status-fail')}>
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
                    onClick={() => set('emails', values.emails.filter((e) => e !== address))}
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
          {testResult && !testResult.ok && testResult.message && (
            <p className="text-status-fail max-w-[70ch] text-xs break-all">{testResult.message}</p>
          )}
        </div>
      </Band>

      {error && <ErrorState message={error} onRetry={save} />}

      <div className="border-line flex items-center gap-4 border-t pt-5">
        <button
          type="button"
          onClick={save}
          disabled={!dirty || saving}
          className={cn(
            'rounded-md px-4 py-2 text-sm transition-transform active:translate-y-px',
            !dirty || saving ? 'border-line text-ink-faint cursor-not-allowed border' : 'bg-accent text-white',
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
        <p className="text-ink-faint ms-auto max-w-[46ch] text-end text-xs">{t('automation.enforceNote')}</p>
      </div>
    </motion.div>
  )
}
