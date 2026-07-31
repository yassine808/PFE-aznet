import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { PlusIcon, TrashIcon } from '@phosphor-icons/react'
import {
  api,
  createUser,
  deleteUser,
  useApi,
  type Account,
  type Async,
  type History,
} from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useI18n } from '@/lib/i18n'
import { daysAgoISO } from '@/lib/metrics'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

/**
 * Dashboard accounts and what each one has done.
 *
 * The director sees everyone; a chef sees only themself. That filtering is
 * enforced by the API — /users and /history both narrow by role — so this page
 * never has to be trusted with it. It only decides what to *offer*.
 */

/** Actions the director asked to count, in the order they matter. */
const HEADLINE = ['flag_cleared', 'report_edited', 'settings_saved', 'report_generated'] as const

function hhmm(seconds: number) {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

export function TeamPage() {
  const { t } = useI18n()
  const { user } = useAuth()
  const users = useApi('users', api.users)
  const [selected, setSelected] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isDirector = user?.role === 'directeur'
  const focus = selected ?? user?.id ?? null
  // Keyed by id so switching account refetches instead of showing the previous
  // person's history under the new name.
  const hist = useApi(`history:${focus}`, (s) => api.history(focus ?? undefined, s))

  const remove = async (id: number) => {
    try {
      await deleteUser(id)
      users.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-8 pt-8"
    >
      <div className="flex flex-wrap items-center gap-4">
        <p className="text-ink-faint max-w-[60ch] text-sm">{t('team.intro')}</p>
        {isDirector && (
          <button
            type="button"
            onClick={() => setAdding((v) => !v)}
            className="border-line text-ink-muted hover:text-ink ms-auto flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors"
          >
            <PlusIcon size={13} weight="bold" />
            {t('team.add')}
          </button>
        )}
      </div>

      {adding && isDirector && (
        <NewAccountForm
          onDone={() => {
            setAdding(false)
            users.reload()
          }}
        />
      )}

      {error && <p className="text-status-fail text-xs">{error}</p>}

      <UsersBlock
        users={users}
        focus={focus}
        isDirector={isDirector}
        currentUserId={user?.id}
        onSelect={setSelected}
        onDelete={remove}
      />

      <HistBlock hist={hist} />
    </motion.div>
  )
}

function UsersBlock({
  users,
  focus,
  isDirector,
  currentUserId,
  onSelect,
  onDelete,
}: {
  readonly users: Async<{ users: Account[] }>
  readonly focus: number | null
  readonly isDirector: boolean
  readonly currentUserId: number | undefined
  readonly onSelect: (id: number) => void
  readonly onDelete: (id: number) => void
}) {
  const { t } = useI18n()
  if (users.error) return <ErrorState message={users.error} onRetry={users.reload} />
  if (users.loading) return <Skeleton className="h-24" />
  if ((users.data?.users.length ?? 0) === 0) return <EmptyState body={t('team.empty')} />
  return (
    <ul className="flex flex-wrap gap-3">
      {users.data?.users.map((account) => (
        <AccountChip
          key={account.id}
          account={account}
          active={focus === account.id}
          canDelete={isDirector && account.id !== currentUserId}
          onSelect={() => onSelect(account.id)}
          onDelete={() => onDelete(account.id)}
        />
      ))}
    </ul>
  )
}

function HistBlock({ hist }: { readonly hist: Async<History> }) {
  if (hist.error) return <ErrorState message={hist.error} onRetry={hist.reload} />
  if (hist.loading && !hist.data) return <Skeleton className="h-64" />
  if (hist.data) return <Activity data={hist.data} />
  return null
}

function AccountChip({
  account,
  active,
  canDelete,
  onSelect,
  onDelete,
}: {
  readonly account: Account
  readonly active: boolean
  readonly canDelete: boolean
  readonly onSelect: () => void
  readonly onDelete: () => void
}) {
  const { t, locale } = useI18n()
  return (
    <li
      className={cn(
        'flex items-center gap-3 rounded-xl border px-4 py-3 transition-colors',
        active ? 'border-accent bg-surface' : 'border-line hover:bg-surface',
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        className="flex flex-col items-start gap-0.5 text-start"
      >
        <span className="text-ink text-sm">{account.name}</span>
        <span className="text-ink-faint text-xs">
          {account.email} · {t(`team.role.${account.role}`)}
        </span>
        <span className="text-ink-faint text-[0.6875rem]">
          {account.last_seen_at
            ? `${t('team.lastSeen')} ${new Date(account.last_seen_at).toLocaleString(locale)}`
            : t('team.neverSeen')}
        </span>
      </button>
      {canDelete && (
        <button
          type="button"
          onClick={onDelete}
          aria-label={`${t('team.remove')} ${account.name}`}
          className="text-ink-faint hover:text-status-fail transition-colors"
        >
          <TrashIcon size={14} />
        </button>
      )}
    </li>
  )
}

function Activity({ data }: { readonly data: History }) {
  const { t, locale } = useI18n()

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
            {new Date(days[0].key).toLocaleDateString(locale, { day: 'numeric', month: 'short' })}
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
            {data.actions.map((a) => (
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
      </section>
    </div>
  )
}

function NewAccountForm({ onDone }: { readonly onDone: () => void }) {
  const { t } = useI18n()
  const [values, setValues] = useState({ email: '', name: '', password: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await createUser(values)
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const set = (k: keyof typeof values) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [k]: e.target.value }))

  const FIELD_TYPE: Record<'name' | 'email' | 'password', string> = {
    name: 'text',
    email: 'email',
    password: 'password',
  }

  return (
    <form
      onSubmit={submit}
      className="border-line bg-surface edge flex flex-wrap items-end gap-4 rounded-xl border p-5"
    >
      {(['name', 'email', 'password'] as const).map((field) => (
        <label key={field} className="flex min-w-40 flex-col gap-1.5">
          <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
            {t(`team.${field}`)}
          </span>
          <input
            type={FIELD_TYPE[field]}
            value={values[field]}
            onChange={set(field)}
            required
            autoComplete={field === 'password' ? 'new-password' : undefined}
            className="border-line focus:border-accent text-ink bg-canvas rounded-md border px-3 py-2 text-sm outline-none transition-colors"
          />
        </label>
      ))}

      <button
        type="submit"
        disabled={busy}
        className="bg-accent rounded-md px-3.5 py-2 text-sm text-white transition-transform active:translate-y-px disabled:opacity-50"
      >
        {t('team.create')}
      </button>

      {error && <p className="text-status-fail w-full text-xs">{error}</p>}
    </form>
  )
}
