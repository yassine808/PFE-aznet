import { useState } from 'react'
import { motion } from 'motion/react'
import { SignInIcon } from '@phosphor-icons/react'
import { useAuth } from '@/lib/auth'
import { LOCALES, LOCALE_LABEL, useI18n, type Locale } from '@/lib/i18n'
import { cn } from '@/lib/utils'

/**
 * Shown instead of the app when nobody is signed in.
 *
 * It is a convenience, not the security boundary — every endpoint is gated on
 * the API, so skipping this screen gains an attacker nothing. That is why it
 * can afford to be this simple.
 *
 * The language switcher sits here and not one navigation deeper: a chef who
 * reads Arabic must be able to pick RTL before reading a single line of the
 * form — the only text that exists before login is the login screen itself.
 */
export function LoginPage() {
  const { t, locale, setLocale } = useI18n()
  const { signIn } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await signIn(email.trim(), password)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const blocked = busy || !email.trim() || !password

  // One field style so the two inputs cannot drift apart. The ring is the
  // accent's job (DESIGN.md): a border that merely changes colour is not a
  // focus indicator a keyboard user can find.
  const field =
    'border-line bg-canvas text-ink focus-visible:border-accent focus-visible:ring-accent/30 rounded-md border px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-2'

  return (
    <main className="bg-canvas relative flex min-h-screen items-center justify-center overflow-hidden p-6">
      {/* A single restrained radial accent, so the form does not float on a void.
          Perpetual motion is for the status band; the login screen gets one
          static glow and nothing that moves. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(65% 45% at 50% -5%, var(--accent-halo-min), transparent 72%)',
        }}
      />

      <div className="absolute top-5 ltr:right-5 rtl:left-5">
        <fieldset className="border-line m-0 flex rounded-md border p-0.5">
          <legend className="sr-only">{t('lang.label')}</legend>
          {LOCALES.map((l: Locale) => (
            <button
              key={l}
              type="button"
              onClick={() => setLocale(l)}
              aria-pressed={l === locale}
              className={cn(
                'cursor-pointer rounded px-2 py-1 text-xs transition-colors',
                l === locale
                  ? 'bg-slate-100 text-ink dark:bg-slate-850'
                  : 'text-ink-faint hover:text-ink',
              )}
            >
              {LOCALE_LABEL[l]}
            </button>
          ))}
        </fieldset>
      </div>

      <motion.form
        onSubmit={submit}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 110, damping: 18 }}
        className="flex w-full max-w-sm flex-col gap-6"
      >
        {/* No card. A bordered panel floating on an empty canvas is chrome
            around four controls; the form is the only thing on screen, so it
            does not need a container to say so. */}
        <div className="flex flex-col items-start gap-3">
          <img
            src="/az-bot.png"
            alt=""
            aria-hidden
            className="border-line edge size-10 rounded-full border"
          />
          <div className="flex flex-col gap-1">
            <h1 className="text-ink text-lg">{t('login.title')}</h1>
            <p className="text-ink-faint text-xs">{t('login.subtitle')}</p>
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
              {t('login.email')}
            </span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
              className={field}
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
              {t('login.password')}
            </span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              className={field}
            />
          </label>
        </div>

        {/* Above the button, not below it: the failure belongs beside the fields
            that caused it, and a message under the submit control is read after
            the retry has already been attempted. role="alert" because a sighted
            user sees it appear and a screen reader has to as well. The API
            answers the same way for a wrong password and an unknown address, so
            this stays as vague as the response it shows. */}
        {error && (
          <p role="alert" className="text-status-fail text-xs">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={blocked}
          aria-busy={busy}
          className={cn(
            'focus-visible:ring-accent flex items-center justify-center gap-2 rounded-md px-3.5 py-2.5 text-sm outline-none transition-transform focus-visible:ring-2 active:translate-y-px',
            blocked
              ? 'border-line text-ink-faint cursor-not-allowed border'
              : 'bg-accent cursor-pointer text-white',
          )}
        >
          <SignInIcon size={15} weight="bold" />
          {busy ? t('login.pending') : t('login.submit')}
        </button>

        <p className="text-ink-faint text-center text-[0.6875rem]">{t('login.restricted')}</p>
      </motion.form>
    </main>
  )
}
