import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  BellRingingIcon,
  ClockCountdownIcon,
  PaintBrushIcon,
  PaperPlaneTiltIcon,
  PlugsConnectedIcon,
  TrashIcon,
  UserCircleIcon,
  XIcon,
} from '@phosphor-icons/react'
import { api, putSettings, sendTestMail, useApi, type AppSettings } from '@/lib/api'
import { intlLocaleOf, useI18n } from '@/lib/i18n'
import { useAuth } from '@/lib/auth'
import { useTheme } from '@/lib/theme'
import { REFRESH_CHOICES, useSettings, type Density, type TimeFormat } from '@/lib/settings'
import { SttOrder } from '@/components/stt-order'
import { cn } from '@/lib/utils'

/**
 * Everything that can be configured, in one place.
 *
 * The gear used to open a 288px popover holding three local preferences, while
 * the schedule and the mail recipients lived on the Automation page and the
 * STT order lived in the popover — three places, no one of which answered
 * "what is this thing set to". This is that one place.
 *
 * It does not own the values. Local preferences still live in
 * `lib/settings.tsx` (localStorage) and the server ones still live in
 * `app_settings` behind GET|PUT /settings; the overlay is a second view onto
 * the same state, so an edit here and an edit on the Automation page cannot
 * disagree.
 *
 * Who may write is decided by the API — PUT /settings is director-only and
 * answers 403 otherwise. The `readOnly` flag here is courtesy, not security:
 * it stops a chef from typing into a field whose save is going to be refused.
 */

type Tab = 'appearance' | 'pipeline' | 'automation' | 'notifications' | 'account'

const TABS: { id: Tab; icon: typeof PaintBrushIcon; labelKey: string }[] = [
  { id: 'appearance', icon: PaintBrushIcon, labelKey: 'settings.tab.appearance' },
  { id: 'pipeline', icon: PlugsConnectedIcon, labelKey: 'settings.tab.pipeline' },
  { id: 'automation', icon: ClockCountdownIcon, labelKey: 'settings.tab.automation' },
  { id: 'notifications', icon: BellRingingIcon, labelKey: 'settings.tab.notifications' },
  { id: 'account', icon: UserCircleIcon, labelKey: 'settings.tab.account' },
]

/** A labelled row of mutually exclusive choices — the panel's only control shape. */
function Segmented<T extends string | number>({
  label,
  value,
  onChange,
  options,
}: {
  readonly label: string
  readonly value: T
  readonly onChange: (v: T) => void
  readonly options: { v: T; label: string }[]
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-ink-faint mb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
        {label}
      </legend>
      <div className="border-line inline-flex flex-wrap rounded-md border p-0.5">
        {options.map((o) => (
          <button
            key={String(o.v)}
            type="button"
            onClick={() => onChange(o.v)}
            aria-pressed={value === o.v}
            className={cn(
              'cursor-pointer rounded px-2.5 py-1 text-xs transition-colors',
              value === o.v
                ? 'bg-slate-100 text-ink dark:bg-slate-850'
                : 'text-ink-faint hover:text-ink',
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </fieldset>
  )
}

function Section({ title, children }: { readonly title: string; readonly children: ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <h3 className="text-ink text-sm font-medium">{title}</h3>
      {children}
    </section>
  )
}

/** The server half: schedule and mail recipients, both read through /settings. */
function ServerSettings({
  which,
  readOnly,
}: {
  readonly which: 'automation' | 'notifications'
  readonly readOnly: boolean
}) {
  const { t, locale } = useI18n()
  const stored = useApi('settings', api.settings)
  // 2026-06-01 is a Monday, so index 0 is Monday — the same base as the
  // scheduler's datetime.weekday(), which is what makes 4 mean Friday in both.
  const days = useMemo(() => {
    const fmt = new Intl.DateTimeFormat(intlLocaleOf(locale), { weekday: 'long' })
    return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2026, 5, 1 + i)))
  }, [locale])
  const [draft, setDraft] = useState<AppSettings | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [newEmail, setNewEmail] = useState('')
  const [testing, setTesting] = useState<string | null>(null)

  // The server's values are the starting point; the draft only exists once the
  // operator has touched something, so a poll landing mid-edit cannot overwrite
  // what they are typing.
  const values: AppSettings = draft ?? stored.data?.settings ?? {}
  const set = <K extends keyof AppSettings>(k: K, v: AppSettings[K]) =>
    setDraft({ ...values, [k]: v })

  const save = async () => {
    if (!draft) return
    setSaving(true)
    setError(null)
    try {
      await putSettings(draft)
      setDraft(null)
      setSaved(true)
      stored.reload()
      window.setTimeout(() => setSaved(false), 2500)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  const field =
    'border-line focus:border-accent text-ink bg-canvas rounded-md border px-3 py-2 text-sm outline-none transition-colors disabled:opacity-60'

  if (stored.loading) return <p className="text-ink-faint text-xs">{t('state.loading')}</p>
  if (stored.error) return <p className="text-status-fail text-xs">{stored.error}</p>

  return (
    <div className="flex flex-col gap-6">
      {which === 'automation' && (
        <Section title={t('settings.tab.automation')}>
          <div className="flex flex-wrap items-end gap-4">
            <label className="flex flex-col gap-1.5">
              <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
                {t('automation.dailyAt')}
              </span>
              <input
                type="time"
                disabled={readOnly}
                value={values.daily_time ?? '18:30'}
                onChange={(e) => set('daily_time', e.target.value)}
                className={cn(field, 'tabular')}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
                {t('automation.weeklyOn')}
              </span>
              <select
                disabled={readOnly}
                value={values.weekly_day ?? 4}
                onChange={(e) => set('weekly_day', Number(e.target.value))}
                className={field}
              >
                {/* 0 = Monday, matching datetime.weekday() on the API side. */}
                {[0, 1, 2, 3, 4, 5, 6].map((d) => (
                  <option key={d} value={d}>
                    {days[d]}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
                {t('automation.at')}
              </span>
              <input
                type="time"
                disabled={readOnly}
                value={values.weekly_time ?? '18:00'}
                onChange={(e) => set('weekly_time', e.target.value)}
                className={cn(field, 'tabular')}
              />
            </label>
          </div>
        </Section>
      )}

      {which === 'notifications' && (
        <Section title={t('settings.tab.notifications')}>
          <ul className="flex flex-col gap-2">
            {(values.emails ?? []).map((address) => (
              <li key={address} className="flex items-center gap-2">
                <span className="text-ink min-w-0 flex-1 truncate text-sm">{address}</span>
                <button
                  type="button"
                  onClick={async () => {
                    setTesting(address)
                    setError(null)
                    try {
                      await sendTestMail(address)
                    } catch (err) {
                      setError(err instanceof Error ? err.message : String(err))
                    } finally {
                      setTesting(null)
                    }
                  }}
                  disabled={testing === address}
                  className="border-line text-ink-muted hover:text-ink flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors disabled:opacity-50"
                >
                  <PaperPlaneTiltIcon size={12} />
                  {t('automation.test')}
                </button>
                {!readOnly && (
                  <button
                    type="button"
                    onClick={() =>
                      set('emails', (values.emails ?? []).filter((e) => e !== address))
                    }
                    aria-label={`${t('access.remove')} ${address}`}
                    className="text-ink-faint hover:text-status-fail cursor-pointer rounded p-1 transition-colors"
                  >
                    <TrashIcon size={12} />
                  </button>
                )}
              </li>
            ))}
            {(values.emails ?? []).length === 0 && (
              <li className="text-ink-faint text-xs italic">{t('automation.noEmails')}</li>
            )}
          </ul>

          {!readOnly && (
            <div className="flex items-center gap-2">
              <input
                type="email"
                value={newEmail}
                placeholder="chef@aznet.ma"
                onChange={(e) => setNewEmail(e.target.value)}
                className={cn(field, 'flex-1')}
              />
              <button
                type="button"
                onClick={() => {
                  const address = newEmail.trim()
                  // Loose on purpose: the Test button is the real validation.
                  if (!address.includes('@') || (values.emails ?? []).includes(address)) return
                  set('emails', [...(values.emails ?? []), address])
                  setNewEmail('')
                }}
                className="border-line text-ink-muted hover:text-ink cursor-pointer rounded-md border px-3 py-2 text-xs transition-colors"
              >
                {t('automation.addEmail')}
              </button>
            </div>
          )}
        </Section>
      )}

      {error && <p className="text-status-fail text-xs break-all">{error}</p>}

      {!readOnly && (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={save}
            disabled={!draft || saving}
            className="bg-accent cursor-pointer rounded-md px-3 py-2 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {saving ? t('automation.testing') : t('settings.apply')}
          </button>
          {saved && <span className="text-status-ok text-xs">{t('settings.applied')}</span>}
        </div>
      )}
      {readOnly && <p className="text-ink-faint text-xs italic">{t('settings.readOnly')}</p>}
    </div>
  )
}

export function SettingsOverlay({
  open,
  onClose,
}: {
  readonly open: boolean
  readonly onClose: () => void
}) {
  const { t } = useI18n()
  const { settings, update, reset } = useSettings()
  const { user, signOut } = useAuth()
  const { theme, toggle } = useTheme()
  const [tab, setTab] = useState<Tab>('appearance')
  const isDirector = user?.role === 'directeur'

  // Escape closes, and the page behind stops scrolling while it is open —
  // both of them things a dialog is expected to do and neither of them free.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) onClose()
          }}
        >
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 120, damping: 20 }}
            role="dialog"
            aria-modal="true"
            aria-label={t('settings.title')}
            className="border-line bg-surface edge flex h-[min(44rem,90dvh)] w-[min(56rem,100%)] overflow-hidden rounded-2xl border shadow-2xl shadow-black/20"
          >
            {/* The tab rail. Icons carry a label at every size: an icon-only
                settings rail is a memory test. */}
            <nav
              aria-label={t('settings.title')}
              className="border-line bg-canvas flex w-14 shrink-0 flex-col gap-1 border-e p-2 sm:w-52"
            >
              {TABS.map(({ id, icon: Icon, labelKey }) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={tab === id}
                  onClick={() => setTab(id)}
                  title={t(labelKey)}
                  className={cn(
                    'flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors',
                    tab === id
                      ? 'bg-surface-raised text-ink'
                      : 'text-ink-faint hover:text-ink hover:bg-surface-raised/60',
                  )}
                >
                  <Icon size={16} className="shrink-0" />
                  <span className="hidden truncate sm:inline">{t(labelKey)}</span>
                </button>
              ))}
            </nav>

            <div className="flex min-w-0 flex-1 flex-col">
              <header className="border-line flex shrink-0 items-center justify-between border-b px-5 py-3">
                <p className="text-ink text-sm font-medium">{t('settings.title')}</p>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label={t('settings.close')}
                  className="text-ink-faint hover:text-ink cursor-pointer rounded p-1 transition-colors"
                >
                  <XIcon size={16} />
                </button>
              </header>

              <div className="min-h-0 flex-1 overflow-y-auto p-5">
                {tab === 'appearance' && (
                  <div className="flex flex-col gap-6">
                    <Section title={t('settings.tab.appearance')}>
                      {/* One toggle behind a two-option control: clicking the
                          option already active would otherwise flip the theme
                          the wrong way, because `toggle` takes no argument. */}
                      <Segmented
                        label={t('settings.themeLabel')}
                        value={theme}
                        onChange={(v) => v !== theme && toggle()}
                        options={[
                          { v: 'light', label: t('theme.toLight') },
                          { v: 'dark', label: t('theme.toDark') },
                        ]}
                      />
                      <Segmented<Density>
                        label={t('settings.density')}
                        value={settings.density}
                        onChange={(v) => update({ density: v })}
                        options={[
                          { v: 'comfortable', label: t('settings.comfortable') },
                          { v: 'compact', label: t('settings.compact') },
                        ]}
                      />
                      <Segmented<TimeFormat>
                        label={t('settings.timeFormat')}
                        value={settings.timeFormat}
                        onChange={(v) => update({ timeFormat: v })}
                        options={[
                          { v: '24h', label: t('settings.h24') },
                          { v: '12h', label: t('settings.h12') },
                        ]}
                      />
                      <Segmented<number>
                        label={t('settings.refresh')}
                        value={settings.refreshMs}
                        onChange={(v) => update({ refreshMs: v })}
                        options={REFRESH_CHOICES.map((ms) => ({
                          v: ms,
                          label: ms === 0 ? t('settings.manual') : `${ms / 1000}s`,
                        }))}
                      />
                      <button
                        type="button"
                        onClick={reset}
                        className="text-ink-faint hover:text-ink self-start text-xs underline underline-offset-4 transition-colors"
                      >
                        {t('settings.reset')}
                      </button>
                    </Section>
                  </div>
                )}

                {tab === 'pipeline' && (
                  <div className="flex flex-col gap-6">
                    <Section title={t('settings.tab.pipeline')}>
                      <SttOrder />
                    </Section>
                    {isDirector && (
                      <Section title={t('settings.confidence')}>
                        <div className="flex flex-col gap-2">
                          <div className="flex items-baseline justify-between">
                            <label htmlFor="ov-confidence" className="text-ink-faint text-xs">
                              {t('settings.confidence')}
                            </label>
                            <span className="tabular text-ink text-xs">
                              {settings.confidence.toFixed(2)}
                            </span>
                          </div>
                          <input
                            id="ov-confidence"
                            type="range"
                            min={0.3}
                            max={0.95}
                            step={0.05}
                            value={settings.confidence}
                            onChange={(e) => update({ confidence: Number(e.target.value) })}
                            className="accent-accent w-full"
                          />
                          <p className="text-ink-faint text-xs">{t('settings.confidenceHint')}</p>
                        </div>
                      </Section>
                    )}
                  </div>
                )}

                {tab === 'automation' && (
                  <ServerSettings which="automation" readOnly={!isDirector} />
                )}
                {tab === 'notifications' && (
                  <ServerSettings which="notifications" readOnly={!isDirector} />
                )}

                {tab === 'account' && (
                  <Section title={t('settings.tab.account')}>
                    <dl className="flex flex-col gap-2 text-sm">
                      <div className="flex gap-2">
                        <dt className="text-ink-faint w-24">{t('settings.accountName')}</dt>
                        <dd className="text-ink">{user?.name ?? '—'}</dd>
                      </div>
                      <div className="flex gap-2">
                        <dt className="text-ink-faint w-24">{t('equipe.roleLabel')}</dt>
                        <dd className="text-ink">{user?.role ?? '—'}</dd>
                      </div>
                    </dl>
                    <button
                      type="button"
                      onClick={() => void signOut()}
                      className="border-line text-ink-muted hover:text-status-fail cursor-pointer self-start rounded-md border px-3 py-2 text-xs transition-colors"
                    >
                      {t('auth.signOut')}
                    </button>
                  </Section>
                )}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
