import { useState } from 'react'
import { motion } from 'motion/react'
import { ArrowsClockwiseIcon, PlusIcon, TrashIcon, UserMinusIcon } from '@phosphor-icons/react'
import {
  addTechnician,
  api,
  deletePerson,
  deleteTechnician,
  refreshProfile,
  useApi,
} from '@/lib/api'
import type { Async, Technician } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { ChannelIcon } from '@/components/channel-icon'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

const CHANNELS = ['telegram', 'whatsapp'] as const

export function AccessControlPage() {
  const { t } = useI18n()
  const list = useApi('technicians', api.technicians)

  const [channel, setChannel] = useState<(typeof CHANNELS)[number]>('whatsapp')
  const [externalId, setExternalId] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!externalId.trim() || !name.trim()) return
    setBusy(true)
    setError(null)
    try {
      await addTechnician({
        channel,
        external_id: externalId.trim(),
        name: name.trim(),
        role: role.trim() || undefined,
      })
      setExternalId('')
      setName('')
      setRole('')
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: number) => {
    try {
      await deleteTechnician(id)
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const removePerson = async (id: number) => {
    try {
      await deletePerson(id)
      list.reload()
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
      <p className="text-ink-faint max-w-[70ch] text-sm">{t('access.intro')}</p>

      <form
        onSubmit={submit}
        className="border-line bg-surface edge flex flex-col gap-4 rounded-xl border p-5"
      >
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1.5">
            <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
              {t('inbox.channel')}
            </span>
            <fieldset className="border-line m-0 flex rounded-md border p-0.5">
              <legend className="sr-only">{t('inbox.channel')}</legend>
              {CHANNELS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setChannel(c)}
                  aria-pressed={channel === c}
                  className={cn(
                    'flex items-center gap-1.5 rounded px-2.5 py-1 text-xs capitalize transition-colors',
                    channel === c
                      ? 'bg-slate-100 text-ink dark:bg-slate-850'
                      : 'text-ink-faint hover:text-ink',
                  )}
                >
                  <ChannelIcon channel={c} size={13} />
                  {c}
                </button>
              ))}
            </fieldset>
          </div>

          <Field
            id="ext"
            label={channel === 'telegram' ? t('access.chatId') : t('access.phone')}
            value={externalId}
            onChange={setExternalId}
            placeholder={channel === 'telegram' ? '123456789' : '2126…'}
          />
          <Field
            id="name"
            label={t('col.technicien')}
            value={name}
            onChange={setName}
            placeholder="Yassine"
          />
          <Field
            id="role"
            label={t('access.role')}
            value={role}
            onChange={setRole}
            placeholder="technicien"
          />

          <button
            type="submit"
            disabled={busy || !externalId.trim() || !name.trim()}
            className={cn(
              'flex items-center gap-2 rounded-md px-3.5 py-2 text-sm transition-transform active:translate-y-px',
              busy || !externalId.trim() || !name.trim()
                ? 'border-line text-ink-faint cursor-not-allowed border'
                : 'bg-accent text-white',
            )}
          >
            <PlusIcon size={14} weight="bold" />
            {t('access.add')}
          </button>
        </div>

        {error && <p className="text-status-fail text-xs break-all">{error}</p>}
      </form>

      <TechniciansList
        list={list}
        onRemoveIdentity={remove}
        onRemovePerson={removePerson}
      />

      <p className="text-ink-faint max-w-[70ch] text-xs">{t('access.enforceNote')}</p>
    </motion.div>
  )
}

/**
 * One colleague: their channels side by side, and what the AI knows about them.
 *
 * A card rather than table rows because a person now has a variable number of
 * channels and a paragraph of profile — a table would either repeat the name on
 * every row (the confusion this refactor exists to remove) or need a rowspan
 * that breaks on mobile.
 */
function TechniciansList({
  list,
  onRemoveIdentity,
  onRemovePerson,
}: {
  readonly list: Async<{ technicians: Technician[] }>
  readonly onRemoveIdentity: (id: number) => void
  readonly onRemovePerson: (id: number) => void
}) {
  const { t } = useI18n()
  if (list.error) return <ErrorState message={list.error} onRetry={list.reload} />
  if (list.loading) return <Skeleton className="h-40" />
  if ((list.data?.technicians.length ?? 0) === 0) return <EmptyState body={t('access.empty')} />
  return (
    <ul className="flex flex-col gap-3">
      {list.data?.technicians.map((person) => (
        <PersonCard
          key={person.id}
          person={person}
          onRemoveIdentity={onRemoveIdentity}
          onRemovePerson={onRemovePerson}
          onReload={list.reload}
        />
      ))}
    </ul>
  )
}

function PersonCard({
  person,
  onRemoveIdentity,
  onRemovePerson,
  onReload,
}: {
  readonly person: Technician
  readonly onRemoveIdentity: (id: number) => void
  readonly onRemovePerson: (id: number) => void
  readonly onReload: () => void
}) {
  const { t } = useI18n()
  const [pending, setPending] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)

  const regenerate = async () => {
    setPending(true)
    setFailed(null)
    try {
      const res = await refreshProfile(person.id)
      if (!res.updated) setFailed(res.reason ?? t('access.profileFailed'))
      onReload()
    } catch (err) {
      setFailed(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <li className="border-line bg-surface edge flex flex-col gap-3 rounded-xl border p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-ink text-sm font-medium">{person.name}</span>
        <span className="text-ink-faint text-xs">{person.role || '—'}</span>

        {/* The point of the whole refactor, made visible: two badges, one person. */}
        <span className="flex flex-wrap items-center gap-1.5">
          {person.identities.map((id) => (
            <span
              key={id.id}
              className={cn(
                'border-line text-ink-muted flex items-center gap-1.5 rounded-full border py-0.5 ps-2 pe-1 text-xs',
                !id.active && 'opacity-50',
              )}
            >
              <ChannelIcon channel={id.channel} size={12} />
              <span className="tabular">{id.external_id}</span>
              <button
                type="button"
                onClick={() => onRemoveIdentity(id.id)}
                aria-label={`${t('access.remove')} ${id.channel} ${id.external_id}`}
                className="text-ink-faint hover:text-status-fail p-0.5 transition-colors"
              >
                <TrashIcon size={12} />
              </button>
            </span>
          ))}
        </span>

        <span className="ms-auto flex items-center gap-1">
          <button
            type="button"
            onClick={regenerate}
            disabled={pending}
            aria-label={`${t('access.regenerate')} ${person.name}`}
            className="text-ink-faint hover:text-ink p-1 transition-colors disabled:opacity-40"
          >
            <ArrowsClockwiseIcon size={15} className={cn(pending && 'animate-spin')} />
          </button>
          <button
            type="button"
            onClick={() => onRemovePerson(person.id)}
            aria-label={`${t('access.removePerson')} ${person.name}`}
            className="text-ink-faint hover:text-status-fail p-1 transition-colors"
          >
            <UserMinusIcon size={15} />
          </button>
        </span>
      </div>

      <p className="text-ink-muted max-w-[70ch] text-xs leading-relaxed">
        {person.profile || <span className="text-ink-faint italic">{t('access.noProfile')}</span>}
      </p>
      {failed && <p className="text-status-fail text-xs break-all">{failed}</p>}
    </li>
  )
}

function Field({
  id,
  label,
  value,
  onChange,
  placeholder,
}: {
  readonly id: string
  readonly label: string
  readonly value: string
  readonly onChange: (v: string) => void
  readonly placeholder?: string
}) {
  return (
    <div className="flex min-w-40 flex-col gap-1.5">
      <label htmlFor={id} className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
        {label}
      </label>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="border-line focus:border-accent text-ink bg-canvas placeholder:text-ink-faint rounded-md border px-3 py-2 text-sm outline-none transition-colors"
      />
    </div>
  )
}
