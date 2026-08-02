import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import {
  CheckIcon,
  FlagIcon,
  PaperPlaneRightIcon,
  PencilSimpleIcon,
  SpeakerHighIcon,
  TextAlignLeftIcon,
} from '@phosphor-icons/react'
import { api, patchReport, sendReply, useApi, type ReportRow } from '@/lib/api'
import { isFlagged, num, toISODate, todayISO, clock } from '@/lib/metrics'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { ChannelIcon } from '@/components/channel-icon'
import { ActivityGraphSection } from '@/components/activity-graph-section'
import { cn } from '@/lib/utils'

/** Fields the manager is allowed to correct before the row feeds the day's report. */
const EDITABLE: { field: keyof ReportRow; labelKey: string; long?: boolean }[] = [
  { field: 'resume', labelKey: 'inbox.field.resume', long: true },
  { field: 'chantier', labelKey: 'col.chantier' },
  { field: 'goulottes_m', labelKey: 'metric.goulottes' },
  { field: 'cables_m', labelKey: 'metric.cables' },
  { field: 'observations', labelKey: 'inbox.field.observations', long: true },
]

function MessageCard({ r, onSaved }: { readonly r: ReportRow; readonly onSaved: () => void }) {
  const { t } = useI18n()
  const { settings } = useSettings()
  // Cards read as messages by default; editing is opt-in per message.
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const original = (f: string) => (r as unknown as Record<string, string | undefined>)[f] ?? ''
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
          {r.date} {clock(r.heure, settings.timeFormat, t('time.am'), t('time.pm'))}
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
          <p className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
            {t('inbox.transcript')}
          </p>
          <p className="text-ink-muted mt-1 max-w-[65ch] text-sm break-words">
            {r.rapport_complet}
          </p>
        </div>
      )}

      {voice && (
        <audio
          controls
          preload="none"
          src={r.lien_audio}
          className="mt-3 h-9 w-full max-w-md"
          aria-label={t('inbox.audio')}
        >
          <track kind="captions" />
        </audio>
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
                {t('metric.goulottes')}:{' '}
                <span className="tabular text-ink">{num(r.goulottes_m)} m</span>
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
              <label
                htmlFor={`${r._row}-${field}`}
                className="text-ink-faint text-[0.6875rem] tracking-wide uppercase"
              >
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

/** The manager's answer, sent by the API on the technician's own channels. */
function ReplyComposer({ name }: { readonly name: string }) {
  const { t } = useI18n()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  const send = async () => {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    setBusy(true)
    setError(null)
    setSent(false)
    try {
      await sendReply(name, trimmed)
      setText('')
      setSent(true)
      window.setTimeout(() => setSent(false), 2500)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="border-line border-t p-4">
      <div className="flex items-end gap-3">
        <textarea
          rows={2}
          value={text}
          placeholder={t('inbox.replyPlaceholder', { name })}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void send()
            }
          }}
          className="border-line focus:border-accent text-ink bg-canvas min-h-0 flex-1 resize-none rounded-md border px-3 py-2 text-sm outline-none transition-colors"
        />
        <button
          type="button"
          onClick={send}
          disabled={busy || !text.trim()}
          className={cn(
            'flex shrink-0 items-center gap-2 rounded-md px-4 py-2 text-sm transition-all active:translate-y-px',
            busy || !text.trim()
              ? 'border-line text-ink-faint cursor-not-allowed border'
              : 'bg-accent text-white hover:opacity-90',
          )}
        >
          <PaperPlaneRightIcon size={14} weight="fill" />
          {busy ? t('inbox.sending') : t('inbox.send')}
        </button>
      </div>

      <div className="mt-2 flex items-center justify-between gap-3">
        <p className="text-ink-faint text-[0.6875rem]">{t('inbox.replyHint')}</p>
        {sent && (
          <span className="text-status-ok flex items-center gap-1 text-xs">
            <CheckIcon size={13} weight="bold" />
            {t('inbox.replySent')}
          </span>
        )}
      </div>
      {error && <p className="text-status-fail mt-2 text-xs break-all">{error}</p>}
    </div>
  )
}

export function InboxPage({ initialDate }: { readonly initialDate?: string }) {
  const { t } = useI18n()
  const { settings } = useSettings()
  const reports = useApi('reports', api.reports, settings.refreshMs || undefined)

  const [channel, setChannel] = useState<string>('')
  // The selected person; the rail below is the picker.
  const [who, setWho] = useState<string>('')
  // Seeded from the deep link out of Overview's year graph (#/inbox?date=…).
  const [date, setDate] = useState<string>(initialDate ?? '')

  const all = useMemo(() => [...(reports.data?.reports ?? [])].reverse(), [reports.data])

  const channels = useMemo(
    () => [...new Set(all.map((r) => (r.canal ?? '').trim()).filter(Boolean))],
    [all],
  )

  // Recent users, newest message first. The rail is the conversation list; the
  // channel/date filters narrow it like any list filter.
  const people = useMemo(() => {
    const byName = new Map<string, { name: string; count: number; last: string; channels: Set<string> }>()
    for (const r of all) {
      const name = (r.technicien ?? '').trim()
      if (!name) continue
      if (channel && (r.canal ?? '').trim() !== channel) continue
      if (date && toISODate(r.date) !== date) continue
      let p = byName.get(name)
      if (!p) {
        // `all` runs newest-first, so the first occurrence is the last message.
        p = { name, count: 0, last: `${r.date} ${r.heure ?? ''}`.trim(), channels: new Set() }
        byName.set(name, p)
      }
      p.count += 1
      p.channels.add((r.canal ?? '').trim().toLowerCase())
    }
    return [...byName.values()]
  }, [all, channel, date])

  // Falls back to the most recent person when the picker points at someone the
  // current filters removed, so the window never goes stale mid-filter.
  const active = who && people.some((p) => p.name === who) ? who : (people[0]?.name ?? '')

  // The same filter set the rail was counted with, so the badge and the
  // thread always agree.
  const windowRows = useMemo(
    () =>
      all.filter(
        (r) =>
          (r.technicien ?? '').trim() === active &&
          (channel ? (r.canal ?? '').trim() === channel : true) &&
          (date ? toISODate(r.date) === date : true),
      ),
    [all, active, channel, date],
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
        <Filter
          label={t('inbox.channel')}
          value={channel}
          onChange={setChannel}
          options={channels}
          allLabel={t('inbox.all')}
        />

        <div className="flex items-center gap-2">
          <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
            {t('daily.date')}
          </span>
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

        <span className="tabular text-ink-faint text-xs">{people.length}</span>
      </div>

      <ActivityGraphSection
        rows={all}
        date={date || todayISO()}
        onSelectDay={(iso) => setDate(iso)}
      />

      {people.length === 0 ? (
        <EmptyState body={t('reports.noMatch')} />
      ) : (
        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
          {/* The conversation list: who wrote, how much, and when they last did. */}
          <aside className="border-line bg-surface edge rounded-xl border lg:sticky lg:top-6">
            <h2 className="text-ink-faint border-line border-b px-4 py-3 text-[0.6875rem] font-medium tracking-wide uppercase">
              {t('inbox.people')}
            </h2>
            <ul className="flex max-h-[60vh] flex-col overflow-y-auto">
              {people.map((p) => (
                <li key={p.name}>
                  <button
                    type="button"
                    onClick={() => setWho(p.name)}
                    aria-pressed={active === p.name}
                    className={cn(
                      'flex w-full items-center gap-3 border-s-2 px-4 py-3 text-start transition-colors',
                      active === p.name
                        ? 'border-s-accent bg-accent/5'
                        : 'border-s-transparent hover:bg-slate-100 dark:hover:bg-slate-850',
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="text-ink block truncate text-sm font-medium">{p.name}</span>
                      <span className="text-ink-faint mt-0.5 flex items-center gap-1.5 text-[0.6875rem]">
                        {[...p.channels].map((c) => (
                          <ChannelIcon key={c} channel={c} size={11} />
                        ))}
                        {p.count} {t('inbox.messages')}
                      </span>
                    </span>
                    <span className="tabular text-ink-faint shrink-0 text-[0.6875rem]">
                      {p.last.split(' ')[0]}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          {/* The conversation itself: thread + modify per message, reply at the
              bottom — the reply leaves on the technician's own channels. */}
          <section className="border-line bg-surface edge flex max-h-[72vh] min-h-[24rem] flex-col rounded-xl border">
            <header className="border-line flex items-center gap-3 border-b px-5 py-4">
              <div className="min-w-0 flex-1">
                <h2 className="text-ink truncate text-base font-medium">{active}</h2>
                <p className="text-ink-faint mt-0.5 text-xs">
                  {t('inbox.replyTo', { name: active })}
                </p>
              </div>
              {(() => {
                const p = people.find((x) => x.name === active)
                return p ? (
                  <span className="text-ink-faint flex items-center gap-1.5 text-xs">
                    {[...p.channels].map((c) => (
                      <ChannelIcon key={c} channel={c} size={14} />
                    ))}
                  </span>
                ) : null
              })()}
            </header>

            <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-5">
              {windowRows.length === 0 ? (
                <EmptyState body={t('reports.noMatch')} />
              ) : (
                windowRows.map((r) => (
                  <MessageCard key={r._row} r={r} onSaved={reports.reload} />
                ))
              )}
            </div>

            <ReplyComposer name={active} />
          </section>
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
  readonly label: string
  readonly value: string
  readonly onChange: (v: string) => void
  readonly options: string[]
  readonly allLabel: string
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">{label}</span>
      <fieldset className="border-line m-0 flex rounded-md border p-0.5">
        <legend className="sr-only">{label}</legend>
        <button
          type="button"
          onClick={() => onChange('')}
          aria-pressed={value === ''}
          className={cn(
            'rounded px-2 py-1 text-xs transition-colors',
            value === ''
              ? 'bg-slate-100 text-ink dark:bg-slate-850'
              : 'text-ink-faint hover:text-ink',
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
              value === o
                ? 'bg-slate-100 text-ink dark:bg-slate-850'
                : 'text-ink-faint hover:text-ink',
            )}
          >
            {o}
          </button>
        ))}
      </fieldset>
    </div>
  )
}
