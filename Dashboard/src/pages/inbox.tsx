import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { CheckIcon, FlagIcon, PencilSimpleIcon, SpeakerHighIcon, TextAlignLeftIcon } from '@phosphor-icons/react'
import { api, patchReport, useApi, type ReportRow } from '@/lib/api'
import { isFlagged, num, toISODate } from '@/lib/metrics'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { ChannelIcon } from '@/components/channel-icon'
import { cn } from '@/lib/utils'

/** Fields the manager is allowed to correct before the row feeds the day's report. */
const EDITABLE: { field: keyof ReportRow & string; labelKey: string; long?: boolean }[] = [
  { field: 'resume', labelKey: 'inbox.field.resume', long: true },
  { field: 'chantier', labelKey: 'col.chantier' },
  { field: 'goulottes_m', labelKey: 'metric.goulottes' },
  { field: 'cables_m', labelKey: 'metric.cables' },
  { field: 'observations', labelKey: 'inbox.field.observations', long: true },
]

function MessageCard({ r, onSaved }: { r: ReportRow; onSaved: () => void }) {
  const { t } = useI18n()
  // Cards read as messages by default; editing is opt-in per message.
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const original = (f: string) => ((r as unknown as Record<string, string | undefined>)[f] ?? '')
  const value = (f: string) => draft[f] ?? original(f)
  const dirty = Object.entries(draft).filter(([f, v]) => v !== original(f))

  const save = async () => {
    if (dirty.length === 0) return
    setSaving(true)
    setError(null)
    try {
      // One PATCH per changed cell: the API writes a single cell per call.
      for (const [field, v] of dirty) await patchReport(r._row, field, v)
      setSaved(true)
      setDraft({})
      onSaved()
      window.setTimeout(() => setSaved(false), 2500)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  const flagged = isFlagged(r.flag_review)
  const voice = Boolean((r.lien_audio ?? '').trim())

  return (
    <article className="border-line bg-surface edge rounded-xl border p-5">
      <header className="border-line flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b pb-3">
        <span className="text-ink-muted flex items-center gap-1.5 text-xs capitalize">
          <ChannelIcon channel={(r.canal ?? '').trim().toLowerCase()} size={13} />
          {r.canal || '—'}
        </span>
        <span className="text-ink-faint flex items-center gap-1 text-xs">
          {voice ? <SpeakerHighIcon size={12} /> : <TextAlignLeftIcon size={12} />}
          {voice ? t('inbox.audio') : t('inbox.text')}
        </span>
        <span className="text-ink text-sm font-medium">{r.technicien || '—'}</span>
        <span className="tabular text-ink-faint text-xs">
          {r.date} {r.heure}
        </span>
        {flagged && (
          <span className="text-status-warn ms-auto flex items-center gap-1 text-xs">
            <FlagIcon size={12} weight="fill" />
            {t('metric.flagged')}
          </span>
        )}
      </header>

      {/* What actually arrived, kept verbatim and never editable: it is the evidence. */}
      {r.rapport_complet && (
        <div className="mt-3">
          <p className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">{t('inbox.transcript')}</p>
          <p className="text-ink-muted mt-1 max-w-[65ch] text-sm break-words">{r.rapport_complet}</p>
        </div>
      )}

      {voice && (
        <audio
          controls
          preload="none"
          src={r.lien_audio}
          className="mt-3 h-9 w-full max-w-md"
          aria-label={t('inbox.audio')}
        />
      )}

      {/* Read view: the generated summary and figures as they stand today. */}
      {!editing && (
        <div className="mt-3 flex flex-col gap-3">
          {r.resume && <p className="text-ink max-w-[70ch] text-sm leading-relaxed">{r.resume}</p>}

          <div className="text-ink-muted flex flex-wrap gap-x-6 gap-y-1 text-xs">
            {r.chantier && (
              <span>
                {t('col.chantier')}: <span className="text-ink">{r.chantier}</span>
              </span>
            )}
            {num(r.goulottes_m) > 0 && (
              <span>
                {t('metric.goulottes')}: <span className="tabular text-ink">{num(r.goulottes_m)} m</span>
              </span>
            )}
            {num(r.cables_m) > 0 && (
              <span>
                {t('metric.cables')}: <span className="tabular text-ink">{num(r.cables_m)} m</span>
              </span>
            )}
            {r.observations && (
              <span>
                {t('inbox.field.observations')}: <span className="text-ink">{r.observations}</span>
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={() => setEditing(true)}
            className="border-line text-ink-muted hover:text-ink flex w-fit items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors active:translate-y-px"
          >
            <PencilSimpleIcon size={13} />
            {t('inbox.modify')}
          </button>
        </div>
      )}

      {editing && (
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {EDITABLE.map(({ field, labelKey, long }) => (
          <div key={field} className={cn('flex flex-col gap-1.5', long && 'sm:col-span-2')}>
            <label htmlFor={`${r._row}-${field}`} className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
              {t(labelKey)}
            </label>
            {long ? (
              <textarea
                id={`${r._row}-${field}`}
                rows={3}
                value={value(field)}
                onChange={(e) => setDraft((d) => ({ ...d, [field]: e.target.value }))}
                className="border-line focus:border-accent text-ink bg-canvas rounded-md border px-3 py-2 text-sm outline-none transition-colors"
              />
            ) : (
              <input
                id={`${r._row}-${field}`}
                value={value(field)}
                onChange={(e) => setDraft((d) => ({ ...d, [field]: e.target.value }))}
                className="border-line focus:border-accent text-ink bg-canvas rounded-md border px-3 py-2 text-sm outline-none transition-colors"
              />
            )}
          </div>
        ))}
      </div>
      )}

      {error && <p className="text-status-fail mt-3 text-xs break-all">{error}</p>}

      {editing && (
      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={dirty.length === 0 || saving}
          className={cn(
            'rounded-md px-3 py-1.5 text-xs transition-colors active:translate-y-px',
            dirty.length === 0 || saving
              ? 'border-line text-ink-faint cursor-not-allowed border'
              : 'bg-accent text-white',
          )}
        >
          {saving ? t('inbox.saving') : t('inbox.save')}
        </button>
        {dirty.length > 0 && !saving && (
          <span className="tabular text-ink-faint text-xs">{dirty.length}</span>
        )}
        <button
          type="button"
          onClick={() => {
            setDraft({})
            setEditing(false)
          }}
          className="text-ink-faint hover:text-ink text-xs underline underline-offset-4 transition-colors"
        >
          {t('inbox.cancel')}
        </button>

        {saved && (
          <span className="text-status-ok flex items-center gap-1 text-xs">
            <CheckIcon size={13} weight="bold" />
            {t('inbox.saved')}
          </span>
        )}
      </div>
      )}
    </article>
  )
}

export function InboxPage({ initialDate }: { initialDate?: string }) {
  const { t } = useI18n()
  const { settings } = useSettings()
  const reports = useApi('reports', api.reports, settings.refreshMs || undefined)

  const [channel, setChannel] = useState<string>('')
  const [who, setWho] = useState<string>('')
  // Seeded from the deep link out of Overview's year graph (#/inbox?date=…).
  const [date, setDate] = useState<string>(initialDate ?? '')

  const all = useMemo(() => [...(reports.data?.reports ?? [])].reverse(), [reports.data])

  const channels = useMemo(
    () => [...new Set(all.map((r) => (r.canal ?? '').trim()).filter(Boolean))],
    [all],
  )
  const people = useMemo(
    () => [...new Set(all.map((r) => (r.technicien ?? '').trim()).filter(Boolean))],
    [all],
  )

  const rows = useMemo(
    () =>
      all
        .filter((r) => (channel ? (r.canal ?? '').trim() === channel : true))
        .filter((r) => (who ? (r.technicien ?? '').trim() === who : true))
        .filter((r) => (date ? toISODate(r.date) === date : true)),
    [all, channel, who, date],
  )

  if (reports.error) return <ErrorState message={reports.error} onRetry={reports.reload} />
  if (reports.loading) {
    return (
      <div className="flex flex-col gap-4 pt-8">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-56 rounded-xl" />
        ))}
      </div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-6 pt-8"
    >
      <p className="text-ink-faint max-w-[65ch] text-sm">{t('inbox.intro')}</p>

      <div className="flex flex-wrap items-center gap-4">
        <Filter label={t('inbox.channel')} value={channel} onChange={setChannel} options={channels} allLabel={t('inbox.all')} />
        <Filter label={t('col.technicien')} value={who} onChange={setWho} options={people} allLabel={t('inbox.all')} />

        <div className="flex items-center gap-2">
          <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">{t('daily.date')}</span>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="border-line focus:border-accent text-ink bg-canvas tabular rounded-md border px-2 py-1 text-xs outline-none transition-colors"
          />
          {date && (
            <button
              type="button"
              onClick={() => setDate('')}
              className="text-ink-faint hover:text-ink text-xs underline underline-offset-4"
            >
              {t('inbox.all')}
            </button>
          )}
        </div>

        <span className="tabular text-ink-faint text-xs">{rows.length}</span>
      </div>

      {rows.length === 0 ? (
        <EmptyState body={t('reports.noMatch')} />
      ) : (
        <div className="flex flex-col gap-4">
          {rows.map((r) => (
            <MessageCard key={r._row} r={r} onSaved={reports.reload} />
          ))}
        </div>
      )}
    </motion.div>
  )
}

function Filter({
  label,
  value,
  onChange,
  options,
  allLabel,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: string[]
  allLabel: string
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">{label}</span>
      <div className="border-line flex rounded-md border p-0.5" role="group" aria-label={label}>
        <button
          type="button"
          onClick={() => onChange('')}
          aria-pressed={value === ''}
          className={cn(
            'rounded px-2 py-1 text-xs transition-colors',
            value === '' ? 'bg-slate-100 text-ink dark:bg-slate-850' : 'text-ink-faint hover:text-ink',
          )}
        >
          {allLabel}
        </button>
        {options.map((o) => (
          <button
            key={o}
            type="button"
            onClick={() => onChange(o)}
            aria-pressed={value === o}
            className={cn(
              'rounded px-2 py-1 text-xs transition-colors',
              value === o ? 'bg-slate-100 text-ink dark:bg-slate-850' : 'text-ink-faint hover:text-ink',
            )}
          >
            {o}
          </button>
        ))}
      </div>
    </div>
  )
}
