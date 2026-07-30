import { useState } from 'react'
import { motion } from 'motion/react'
import { SignInIcon } from '@phosphor-icons/react'
import { useAuth } from '@/lib/auth'
import { useI18n } from '@/lib/i18n'
import { cn } from '@/lib/utils'

/**
 * Shown instead of the app when nobody is signed in.
 *
 * It is a convenience, not the security boundary — every endpoint is gated on
 * the API, so skipping this screen gains an attacker nothing. That is why it
 * can afford to be this simple.
 */
export function LoginPage() {
  const { t } = useI18n()
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

  return (
    <main className="bg-canvas flex min-h-screen items-center justify-center p-6">
      <motion.form
        onSubmit={submit}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 110, damping: 18 }}
        className="border-line bg-surface edge flex w-full max-w-sm flex-col gap-5 rounded-xl border p-7"
      >
        <div className="flex flex-col gap-1">
          <h1 className="text-ink text-lg">{t('login.title')}</h1>
          <p className="text-ink-faint text-xs">{t('login.subtitle')}</p>
        </div>

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
            className="border-line focus:border-accent text-ink bg-canvas rounded-md border px-3 py-2 text-sm outline-none transition-colors"
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
            className="border-line focus:border-accent text-ink bg-canvas rounded-md border px-3 py-2 text-sm outline-none transition-colors"
          />
        </label>

        <button
          type="submit"
          disabled={busy || !email.trim() || !password}
          className={cn(
            'flex items-center justify-center gap-2 rounded-md px-3.5 py-2.5 text-sm transition-transform active:translate-y-px',
            busy || !email.trim() || !password
              ? 'border-line text-ink-faint cursor-not-allowed border'
              : 'bg-accent text-white',
          )}
        >
          <SignInIcon size={15} weight="bold" />
          {busy ? t('login.pending') : t('login.submit')}
        </button>

        {/* The API answers the same way for a wrong password and an unknown
            address, so this message stays as vague as the response it shows. */}
        {error && <p className="text-status-fail text-xs">{error}</p>}
      </motion.form>
    </main>
  )
}
