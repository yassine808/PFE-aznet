import { useState } from 'react'
import { motion } from 'motion/react'
import { PlusIcon, TrashIcon } from '@phosphor-icons/react'
import { addTechnician, api, deleteTechnician, useApi } from '@/lib/api'
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
      await addTechnician({ channel, external_id: externalId.trim(), name: name.trim(), role: role.trim() || undefined })
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

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-8 pt-8"
    >
      <p className="text-ink-faint max-w-[70ch] text-sm">{t('access.intro')}</p>

      <form onSubmit={submit} className="border-line bg-surface edge flex flex-col gap-4 rounded-xl border p-5">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1.5">
            <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">{t('inbox.channel')}</span>
            <div className="border-line flex rounded-md border p-0.5" role="group" aria-label={t('inbox.channel')}>
              {CHANNELS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setChannel(c)}
                  aria-pressed={channel === c}
                  className={cn(
                    'flex items-center gap-1.5 rounded px-2.5 py-1 text-xs capitalize transition-colors',
                    channel === c ? 'bg-slate-100 text-ink dark:bg-slate-850' : 'text-ink-faint hover:text-ink',
                  )}
                >
                  <ChannelIcon channel={c} size={13} />
                  {c}
                </button>
              ))}
            </div>
          </div>

          <Field
            id="ext"
            label={channel === 'telegram' ? t('access.chatId') : t('access.phone')}
            value={externalId}
            onChange={setExternalId}
            placeholder={channel === 'telegram' ? '123456789' : '2126…'}
          />
          <Field id="name" label={t('col.technicien')} value={name} onChange={setName} placeholder="Yassine" />
          <Field id="role" label={t('access.role')} value={role} onChange={setRole} placeholder="technicien" />

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

      {list.error ? (
        <ErrorState message={list.error} onRetry={list.reload} />
      ) : list.loading ? (
        <Skeleton className="h-40" />
      ) : (list.data?.technicians.length ?? 0) === 0 ? (
        <EmptyState body={t('access.empty')} />
      ) : (
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-line text-ink-faint border-b text-[0.6875rem] tracking-wide uppercase">
              <th className="py-2 pe-4 text-start font-medium">{t('inbox.channel')}</th>
              <th className="py-2 pe-4 text-start font-medium">{t('access.identifier')}</th>
              <th className="py-2 pe-4 text-start font-medium">{t('col.technicien')}</th>
              <th className="py-2 pe-4 text-start font-medium">{t('access.role')}</th>
              <th className="py-2 text-end font-medium">
                <span className="sr-only">{t('access.remove')}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {list.data?.technicians.map((tech) => (
              <tr key={tech.id} className="border-line hover:bg-surface border-b transition-colors last:border-b-0">
                <td className="py-3 pe-4 text-sm">
                  <span className="text-ink-muted flex items-center gap-2 capitalize">
                    <ChannelIcon channel={tech.channel} size={14} />
                    {tech.channel}
                  </span>
                </td>
                <td className="tabular text-ink py-3 pe-4 text-sm">{tech.external_id}</td>
                <td className="text-ink py-3 pe-4 text-sm">{tech.name}</td>
                <td className="text-ink-muted py-3 pe-4 text-sm">{tech.role || '—'}</td>
                <td className="py-3 text-end">
                  <button
                    type="button"
                    onClick={() => remove(tech.id)}
                    aria-label={`${t('access.remove')} ${tech.name}`}
                    className="text-ink-faint hover:text-status-fail transition-colors"
                  >
                    <TrashIcon size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <p className="text-ink-faint max-w-[70ch] text-xs">{t('access.enforceNote')}</p>
    </motion.div>
  )
}

function Field({
  id,
  label,
  value,
  onChange,
  placeholder,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
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
