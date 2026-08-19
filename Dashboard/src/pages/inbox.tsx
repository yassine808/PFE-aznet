import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  CalendarBlankIcon,
  CaretDownIcon,
  CheckIcon,
  ChecksIcon,
  FlagIcon,
  HourglassMediumIcon,
  PaperPlaneRightIcon,
  PencilSimpleIcon,
  ImageIcon,
  SpeakerHighIcon,
  TextAlignLeftIcon,
  UserIcon,
  UsersThreeIcon,
} from '@phosphor-icons/react'
import {
  api,
  audioByRow,
  audioSrc,
  mediaSrc,
  patchExchange,
  patchReport,
  sendReply,
  useApi,
  type ReportRow,
  type Identity,
  type Technician,
} from '@/lib/api'
import { isFlagged, num, toISODate, todayISO, daysAgoISO, parseISODay, clock } from '@/lib/metrics'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { ChannelIcon } from '@/components/channel-icon'
import { ActivityGraphSection } from '@/components/activity-graph-section'
import { cn, formatPhone } from '@/lib/utils'

/**
 * The inbox, as the conversation it actually is.
 *
 * Every row of the Sheet is one exchange: the technician sent a voice note or a
 * message, and the bot answered with the summary it extracted. The page used to
 * render that as a stack of record cards — a header, a labelled transcript
 * block, a labelled figures block, an edit form — which is a database view of
 * something that happened as a chat, and made three nested scroll regions out of
 * one screen.
 *
 * It is now a thread: incoming on the start side, the bot's reply on the end
 * side, day separators between them, one composer pinned at the bottom. Nothing
 * about the data changed — the transcript is still verbatim and still the
 * evidence, the summary is still the editable part. What changed is that the
 * order and the sides say who spoke, so the labels that used to say it can go.
 *
 * One scroll region, not four: the page fills the viewport, the rail and the
 * thread each own their overflow, and the year heatmap — a picker, not a
 * reading surface — collapses out of the way.
 */

/** Fields the manager is allowed to correct before the row feeds the day's report. */
const EDITABLE: { field: keyof ReportRow; labelKey: string; long?: boolean }[] = [
  { field: 'resume', labelKey: 'inbox.field.resume', long: true },
  { field: 'chantier', labelKey: 'col.chantier' },
  { field: 'goulottes_m', labelKey: 'metric.goulottes' },
  { field: 'cables_m', labelKey: 'metric.cables' },
  { field: 'arrets_min', labelKey: 'inbox.field.arrets' },
  { field: 'motif_arret', labelKey: 'inbox.field.motif' },
  { field: 'besoins', labelKey: 'inbox.field.besoins', long: true },
  { field: 'prochaines_etapes', labelKey: 'inbox.field.etapes', long: true },
  { field: 'observations', labelKey: 'inbox.field.observations', long: true },
]

/**
 * A day's worth of exchanges, oldest first.
 *
 * Rows arrive newest-first from the rail's ordering; a chat reads the other way,
 * and the composer sits at the bottom, so each day's messages are re-sorted here
 * rather than the whole list being reversed twice on the way in.
 */
interface Day {
  readonly iso: string
  readonly rows: ThreadRow[]
}

/**
 * A message in the thread: either a Sheet row (a report that was filed) or a
 * logged exchange (a message that never became one). The two are the same
 * conversation — the reply the technician got either lives in the row's
 * `resume` or in the exchange's `reply` — so they share one timeline.
 */
type ThreadRow = ReportRow | ThreadExchange

/** One recorded exchange, shaped like the fields the thread reads. */
interface ThreadExchange {
  /** `x<id>` — a string that can never collide with a Sheet row number. */
  readonly _row: string
  /** The `exchanges` primary key, kept alongside `_row` because a transcript
   *  correction addresses the row itself (`PATCH /exchanges/{id}`) and parsing
   *  it back out of the prefixed string would be a second place to get wrong. */
  readonly id: number
  readonly date: string
  readonly heure?: string
  readonly canal?: string
  readonly technicien?: string
  readonly kind?: string
  readonly text?: string
  /** Required (may hold `undefined`): the thread discriminates with `'reply' in
   *  r`, and an optional property would keep exchanges in the false branch. */
  readonly reply: string | undefined
  readonly media_id?: number | null
  readonly stt_engine?: string | null
  readonly correlation_id?: string | null
}

function groupByDay(rows: ThreadRow[]): Day[] {
  const byDay = new Map<string, ThreadRow[]>()
  for (const r of rows) {
    const iso = toISODate(r.date) ?? (r.date ?? '').trim() ?? ''
    const bucket = byDay.get(iso)
    if (bucket) bucket.push(r)
    else byDay.set(iso, [r])
  }
  // Oldest day first, and within a day oldest message first: the newest thing
  // ends up next to the composer, which is where the eye already is.
  return [...byDay.entries()]
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([iso, dayRows]) => ({
      iso,
      rows: [...dayRows].sort((a, b) => (a.heure ?? '').localeCompare(b.heure ?? '')),
    }))
}

/**
 * `Aujourd'hui` / `Hier` / a written date.
 *
 * Shared by the separator between days and the floating marker that follows the
 * scroll, so the two can never disagree about what a day is called.
 */
function useDayLabel() {
  const { t, locale } = useI18n()
  return (iso: string) => {
    if (iso === todayISO()) return t('graph.today')
    if (iso === daysAgoISO(1)) return t('inbox.yesterday')
    if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
      return parseISODay(iso).toLocaleDateString(locale, {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
      })
    }
    return iso
  }
}

/** The separator WhatsApp puts between days. */
function DaySeparator({ iso }: { readonly iso: string }) {
  const label = useDayLabel()(iso)
  return (
    <div className="sticky top-0 z-10 flex justify-center py-2">
      <span className="border-line bg-canvas text-ink-faint rounded-full border px-3 py-1 text-[0.6875rem] capitalize">
        {label}
      </span>
    </div>
  )
}

/**
 * One bubble's timestamp, in the corner the platform puts it.
 *
 * `sent` adds the double tick every messaging app uses for "it left here".
 * It is deliberately not a read receipt — the channel never tells us that, and
 * a tick that claims more than we know is worse than no tick.
 */
function Stamp({ heure, sent = false }: { readonly heure?: string; readonly sent?: boolean }) {
  const { t } = useI18n()
  const { settings } = useSettings()
  return (
    <span className="tabular text-ink-faint flex items-center gap-1 text-[0.625rem]">
      {clock(heure, settings.timeFormat, t('time.am'), t('time.pm'))}
      {sent && <ChecksIcon size={12} className="text-accent" aria-label={t('inbox.delivered')} />}
    </span>
  )
}

/**
 * The transcript of a voice note, under the player it belongs to, correctable.
 *
 * It used to be printed as plain text on the rule that a transcript is
 * evidence and correcting it would make the extraction unauditable. The rule
 * was right about the risk and wrong about the remedy: Darija through an STT
 * engine gets names and quantities wrong, and the only person who can say so
 * is the one listening to the recording — leaving them a wrong transcript they
 * can read but not fix does not preserve the evidence, it just preserves the
 * error. Both write paths (`PATCH /reports/{row}` and `PATCH /exchanges/{id}`)
 * record the previous value against the account that changed it, so the raw
 * machine output stays recoverable from the audit trail. That is what makes
 * this safe, and it is why the correction must never be written any other way.
 *
 * Shown only for audio. A typed message has no transcript to correct — its
 * text *is* what the technician wrote, and offering to edit it would invite
 * rewriting what somebody said.
 */
function TranscriptBubble({
  id,
  text,
  engine,
  save,
  onSaved,
}: {
  /** Unique per message — the label/textarea pairing needs a stable id. */
  readonly id: string
  readonly text: string
  /** Which engine produced this text. It belongs next to the transcript and
   *  nowhere else: the chain falls through on failure, so `local` here means
   *  both cloud engines were unavailable at that moment — and reading a wrong
   *  number is a different judgement depending on which engine heard it. It
   *  was removed from the technician's reply on purpose (that is operations,
   *  not site work); this is the operator's screen, where it is the point. */
  readonly engine?: string
  readonly save: (value: string) => Promise<void>
  readonly onSaved: () => void
}) {
  const { t } = useI18n()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(text)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dirty = draft.trim() !== text.trim()

  const commit = async () => {
    if (!dirty) return setEditing(false)
    setSaving(true)
    setError(null)
    try {
      await save(draft.trim())
      setEditing(false)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="border-line bg-canvas/60 flex flex-col gap-1.5 rounded-lg border px-3 py-2">
      <div className="text-ink-faint flex items-center gap-2 text-[0.625rem] tracking-wide uppercase">
        {t('inbox.transcript')}
        {engine && (
          <span
            className="border-line text-ink-muted rounded-full border px-1.5 py-px normal-case"
            title={t('inbox.sttEngine')}
          >
            {engine}
          </span>
        )}
        <button
          type="button"
          onClick={() => {
            setDraft(text)
            setError(null)
            setEditing((v) => !v)
          }}
          aria-expanded={editing}
          className="text-ink-faint hover:text-ink ms-auto flex cursor-pointer items-center gap-1 normal-case transition-colors"
        >
          <PencilSimpleIcon size={11} />
          {editing ? t('inbox.cancel') : t('inbox.modify')}
        </button>
      </div>

      {editing ? (
        <>
          <label htmlFor={`transcript-${id}`} className="sr-only">
            {t('inbox.transcript')}
          </label>
          <textarea
            id={`transcript-${id}`}
            rows={4}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="border-line focus:border-accent text-ink bg-surface rounded-md border px-3 py-2 text-sm outline-none transition-colors"
          />
          {error && <p className="text-status-fail text-xs break-all">{error}</p>}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void commit()}
              disabled={!dirty || saving}
              className={cn(
                'rounded-md px-3 py-1 text-xs transition-colors active:translate-y-px',
                !dirty || saving
                  ? 'border-line text-ink-faint cursor-not-allowed border'
                  : 'bg-accent cursor-pointer text-white',
              )}
            >
              {saving ? t('inbox.saving') : t('inbox.save')}
            </button>
          </div>
        </>
      ) : (
        <p className="text-ink text-sm break-words whitespace-pre-wrap">{text}</p>
      )}
    </div>
  )
}

/**
 * What the technician sent: the audio, and under it the transcript it produced.
 */
function IncomingBubble({
  r,
  address,
  onSaved,
}: {
  readonly r: ReportRow
  readonly address?: string
  readonly onSaved: () => void
}) {
  const { t } = useI18n()
  /*
    The Drive copy first, the archived blob if it cannot answer.

    A Drive file can be missing, unshared, or the upload may have failed at
    reception — in which case the API still holds the bytes. `onError` is the
    only signal a media element gives us (it does not report status codes), so
    one retry against the row route turns a silent dead player into a working
    one. Guarded by a flag: without it a genuinely absent recording would
    bounce between the two sources forever.
  */
  const [fallback, setFallback] = useState(false)
  const [dead, setDead] = useState(false)
  const primary = audioSrc(r.lien_audio, r._row)
  const src = dead ? null : fallback ? audioByRow(r._row) : primary
  const voice = src !== null

  return (
    <div className="flex justify-start">
      <div className="bubble bubble-in border-line bg-surface-raised flex max-w-[min(46rem,85%)] flex-col gap-2 rounded-2xl rounded-ss-sm border px-4 py-3">
        <div className="text-ink-faint flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[0.625rem]">
          <ChannelIcon channel={(r.canal ?? '').trim().toLowerCase()} size={12} />
          {/* The WhatsApp number or Telegram chat id this arrived on. One person
              can write from several, so which one is a fact about the message,
              not about them — it belongs on the message. `tabular` because it is
              a number being read digit by digit against another one. */}
          {address && <span className="tabular select-all">{address}</span>}
          <span className="flex items-center gap-1">
            {voice ? <SpeakerHighIcon size={11} /> : <TextAlignLeftIcon size={11} />}
            {voice ? t('inbox.audio') : t('inbox.text')}
          </span>
        </div>

        {src && (
          <audio
            controls
            preload="none"
            src={src}
            onError={() => (fallback ? setDead(true) : setFallback(true))}
            className="h-9 w-full min-w-[16rem]"
            aria-label={t('inbox.audio')}
          >
            <track kind="captions" />
          </audio>
        )}

        {/* For a voice note the text below the player *is* the transcript, so
            it gets the correctable treatment; for a typed message it is what
            the technician wrote, and stays as written. */}
        {r.rapport_complet &&
          (voice ? (
            <TranscriptBubble
              id={`row-${r._row}`}
              text={r.rapport_complet}
              engine={r.STT_model}
              save={(value) => patchReport(r._row, 'rapport_complet', value)}
              onSaved={onSaved}
            />
          ) : (
            <p className="text-ink text-sm break-words whitespace-pre-wrap">{r.rapport_complet}</p>
          ))}

        <Stamp heure={r.heure} />
      </div>
    </div>
  )
}

/**
 * What the technician sent, when it never became a Sheet row.
 *
 * Same shell as IncomingBubble, but there is no Drive link and no row route —
 * the media blob in Postgres is the only copy, so the audio plays straight
 * from it, and the transcript is whatever shape the message took.
 */
function ExchangeIncoming({
  r,
  address,
  onSaved,
}: {
  readonly r: ThreadExchange
  readonly address?: string
  readonly onSaved: () => void
}) {
  const { t } = useI18n()
  const src = r.media_id != null ? mediaSrc(r.media_id) : null
  /*
    A photo report archives an image blob in the same column an audio note uses,
    and this bubble fed every blob to an `<audio>` element: the picture the
    technician sent rendered as a player that plays nothing and says "Note
    vocale". `kind` is what the two shapes differ by, and n8n has always sent it.
  */
  const photo = (r.kind ?? '').trim().toLowerCase() === 'image'
  const voice = src !== null && !photo

  return (
    <div className="flex justify-start">
      <div className="bubble bubble-in border-line bg-surface-raised flex max-w-[min(46rem,85%)] flex-col gap-2 rounded-2xl rounded-ss-sm border px-4 py-3">
        <div className="text-ink-faint flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[0.625rem]">
          <ChannelIcon channel={(r.canal ?? '').trim().toLowerCase()} size={12} />
          {address && <span className="tabular select-all">{address}</span>}
          <span className="flex items-center gap-1">
            {photo ? (
              <ImageIcon size={11} />
            ) : voice ? (
              <SpeakerHighIcon size={11} />
            ) : (
              <TextAlignLeftIcon size={11} />
            )}
            {photo ? t('inbox.photo') : voice ? t('inbox.audio') : t('inbox.text')}
          </span>
        </div>

        {src &&
          (photo ? (
            <img
              src={src}
              alt={t('inbox.photo')}
              loading="lazy"
              className="border-line max-h-80 w-auto max-w-full rounded-lg border object-contain"
            />
          ) : (
            <audio
              controls
              preload="none"
              src={src}
              className="h-9 w-full min-w-[16rem]"
              aria-label={t('inbox.audio')}
            >
              <track kind="captions" />
            </audio>
          ))}

        {r.text &&
          (voice ? (
            <TranscriptBubble
              id={`exchange-${r.id}`}
              text={r.text}
              engine={r.stt_engine ?? undefined}
              save={(value) => patchExchange(r.id, value)}
              onSaved={onSaved}
            />
          ) : (
            <p className="text-ink text-sm break-words whitespace-pre-wrap">{r.text}</p>
          ))}

        <Stamp heure={r.heure} />
      </div>
    </div>
  )
}

/**
 * What the bot answered, when there is no Sheet row behind it.
 *
 * The reply is a fact of the log, not a draft — nothing about it can be
 * corrected here because there is no row to correct.
 */
function ExchangeReply({ r }: { readonly r: ThreadExchange }) {
  const { t } = useI18n()
  return (
    <div className="flex justify-end">
      <div className="bubble bubble-out border-accent/20 bg-accent/5 flex max-w-[min(46rem,85%)] flex-col gap-2 rounded-2xl rounded-se-sm border px-4 py-3">
        <div className="text-ink-faint flex items-center gap-2 text-[0.625rem]">
          <span className="tracking-wide uppercase">{t('inbox.bot')}</span>
        </div>

        {r.reply ? (
          <p className="text-ink text-sm leading-relaxed break-words whitespace-pre-wrap">
            {r.reply}
          </p>
        ) : (
          <p className="text-ink-faint text-sm italic">{t('inbox.noReply')}</p>
        )}

        <Stamp heure={r.heure} sent />
      </div>
    </div>
  )
}

/**
 * What the bot answered: the summary the technician actually received, the
 * figures it pulled out, and the way in to correcting them.
 *
 * The editor is collapsed behind one control rather than sitting under every
 * message: a nine-field form repeated down a thread is the record view this
 * page was moving away from.
 */
function BotBubble({ r, onSaved }: { readonly r: ReportRow; readonly onSaved: () => void }) {
  const { t } = useI18n()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const original = (f: string) => (r as unknown as Record<string, string | undefined>)[f] ?? ''
  const value = (f: string) => draft[f] ?? original(f)
  const dirty = Object.entries(draft).filter(([f, v]) => v !== original(f))
  const flagged = isFlagged(r.flag_review)

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

  // Only the figures this row actually carries. An absent quantity is left out
  // rather than printed as a zero — "not reported" and "none installed" are the
  // one distinction the whole extraction prompt is built around.
  const facts: { label: string; value: string }[] = []
  if (r.chantier) facts.push({ label: t('col.chantier'), value: r.chantier })
  if (num(r.goulottes_m) > 0)
    facts.push({ label: t('metric.goulottes'), value: `${num(r.goulottes_m)} m` })
  if (num(r.cables_m) > 0) facts.push({ label: t('metric.cables'), value: `${num(r.cables_m)} m` })
  if (num(r.arrets_min) > 0)
    facts.push({ label: t('inbox.field.arrets'), value: `${num(r.arrets_min)} min` })
  if (r.motif_arret) facts.push({ label: t('inbox.field.motif'), value: r.motif_arret })
  if (r.besoins) facts.push({ label: t('inbox.field.besoins'), value: r.besoins })
  if (r.prochaines_etapes)
    facts.push({ label: t('inbox.field.etapes'), value: r.prochaines_etapes })
  if (r.observations) facts.push({ label: t('inbox.field.observations'), value: r.observations })

  return (
    <div className="flex justify-end">
      <div
        className={cn(
          'bubble bubble-out flex max-w-[min(46rem,85%)] flex-col gap-2 rounded-2xl rounded-se-sm border px-4 py-3',
          // The accent tint is the outgoing side, the way every chat client
          // marks "this one is from us". Flagged rows take the attention
          // border instead — one signal at a time, per the Ten Percent Rule.
          flagged ? 'border-status-warn bg-accent/5' : 'border-accent/20 bg-accent/5',
        )}
      >
        <div className="text-ink-faint flex items-center gap-2 text-[0.625rem]">
          <span className="tracking-wide uppercase">{t('inbox.bot')}</span>
          {flagged && (
            <span className="text-status-warn flex items-center gap-1">
              <FlagIcon size={11} weight="fill" />
              {t('metric.flagged')}
            </span>
          )}
        </div>

        {r.resume ? (
          <p className="text-ink text-sm leading-relaxed break-words">{r.resume}</p>
        ) : (
          <p className="text-ink-faint text-sm italic">{t('inbox.noReply')}</p>
        )}

        {facts.length > 0 && (
          <dl className="text-ink-muted flex flex-wrap gap-x-4 gap-y-0.5 text-xs">
            {facts.map((f) => (
              <div key={f.label} className="flex gap-1">
                <dt className="text-ink-faint">{f.label}</dt>
                <dd className="text-ink">{f.value}</dd>
              </div>
            ))}
          </dl>
        )}

        <div className="flex items-center gap-3">
          <Stamp heure={r.heure} sent />
          <button
            type="button"
            onClick={() => setEditing((v) => !v)}
            aria-expanded={editing}
            className="text-ink-faint hover:text-ink ms-auto flex cursor-pointer items-center gap-1 text-[0.6875rem] transition-colors"
          >
            <PencilSimpleIcon size={12} />
            {editing ? t('inbox.cancel') : t('inbox.modify')}
          </button>
          {saved && (
            <span className="text-status-ok flex items-center gap-1 text-[0.6875rem]">
              <CheckIcon size={12} weight="bold" />
              {t('inbox.saved')}
            </span>
          )}
        </div>

        {editing && (
          <div className="border-line mt-1 flex flex-col gap-3 border-t pt-3">
            <div className="grid gap-3 sm:grid-cols-2">
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

            {error && <p className="text-status-fail text-xs break-all">{error}</p>}

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={save}
                disabled={dirty.length === 0 || saving}
                className={cn(
                  'rounded-md px-3 py-1.5 text-xs transition-colors active:translate-y-px',
                  dirty.length === 0 || saving
                    ? 'border-line text-ink-faint cursor-not-allowed border'
                    : 'bg-accent cursor-pointer text-white',
                )}
              >
                {saving ? t('inbox.saving') : t('inbox.save')}
              </button>
              {dirty.length > 0 && !saving && (
                <span className="tabular text-ink-faint text-xs">{dirty.length}</span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * The manager's answer, sent by the API on one of the technician's channels.
 *
 * The destination is not a question the operator should have to answer twice:
 * it defaults to the channel and identity the last message arrived on, shown
 * as a chip. Someone who owns two numbers, or a phone and a Telegram account,
 * clicks the chip and picks. The API still broadcasts when no identity is
 * named, but a private answer sent to every address a technician owns is the
 * mistake this picker exists to prevent, so the inbox always names one.
 */
function ReplyComposer({
  name,
  identities,
  preferred,
}: {
  readonly name: string
  readonly identities: readonly Identity[]
  /** Identity id of the channel the last message arrived on, when known. */
  readonly preferred?: number
}) {
  const { t } = useI18n()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [pickedId, setPickedId] = useState<number | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement | null>(null)

  const active = identities.filter((i) => i.active)
  // The operator's choice wins, then the channel this conversation arrived on,
  // then the only one there is. Never a silent broadcast.
  const target =
    active.find((i) => i.id === pickedId) ?? active.find((i) => i.id === preferred) ?? active[0]

  // A different technician is a different conversation: a pick made for one
  // must not follow the operator into the next person's thread.
  useEffect(() => {
    setPickedId(null)
    setPickerOpen(false)
  }, [name])

  useEffect(() => {
    if (!pickerOpen) return
    const onDown = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) setPickerOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPickerOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [pickerOpen])

  const label = (i: Identity) =>
    i.channel.trim().toLowerCase() === 'whatsapp' ? formatPhone(i.external_id) : i.external_id

  const send = async () => {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    setBusy(true)
    setError(null)
    setSent(false)
    try {
      await sendReply(name, trimmed, target?.id)
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
    <div className="border-line bg-surface shrink-0 border-t p-3">
      {target && (
        <div ref={pickerRef} className="relative mb-2 flex items-center gap-2">
          <span className="text-ink-faint text-[0.625rem]">{t('inbox.sendTo')}</span>
          <button
            type="button"
            onClick={() => active.length > 1 && setPickerOpen((v) => !v)}
            aria-haspopup={active.length > 1 ? 'listbox' : undefined}
            aria-expanded={active.length > 1 ? pickerOpen : undefined}
            disabled={active.length < 2}
            className={cn(
              'border-line text-ink-muted flex items-center gap-1.5 rounded-full border px-2 py-1 text-[0.6875rem] transition-colors',
              active.length > 1 ? 'hover:text-ink cursor-pointer' : 'cursor-default',
            )}
          >
            <ChannelIcon channel={target.channel.trim().toLowerCase()} size={12} />
            <span className="tabular">{label(target)}</span>
            {active.length > 1 && <CaretDownIcon size={10} />}
          </button>

          <AnimatePresence>
            {pickerOpen && (
              <motion.ul
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                transition={{ duration: 0.12 }}
                role="listbox"
                aria-label={t('inbox.sendTo')}
                className="border-line bg-surface-raised edge absolute bottom-full z-30 mb-1.5 min-w-52 overflow-hidden rounded-xl border shadow-xl shadow-black/5 ltr:start-0 rtl:end-0"
              >
                {active.map((i) => (
                  <li key={i.id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={i.id === target.id}
                      onClick={() => {
                        setPickedId(i.id)
                        setPickerOpen(false)
                      }}
                      className={cn(
                        'hover:bg-slate-50 dark:hover:bg-slate-850 flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-start text-xs transition-colors',
                        i.id === target.id && 'text-ink font-medium',
                      )}
                    >
                      <ChannelIcon channel={i.channel.trim().toLowerCase()} size={12} />
                      <span className="tabular flex-1">{label(i)}</span>
                      {i.id === target.id && <CheckIcon size={12} weight="bold" />}
                    </button>
                  </li>
                ))}
              </motion.ul>
            )}
          </AnimatePresence>
        </div>
      )}

      <div className="flex items-end gap-2">
        <textarea
          rows={1}
          value={text}
          placeholder={t('inbox.replyPlaceholder', { name })}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void send()
            }
          }}
          className="border-line focus:border-accent text-ink bg-canvas max-h-32 min-h-0 flex-1 resize-none rounded-full border px-4 py-2.5 text-sm outline-none transition-colors"
        />
        <button
          type="button"
          onClick={send}
          disabled={busy || !text.trim()}
          title={t('inbox.send')}
          aria-label={t('inbox.send')}
          className={cn(
            'flex size-10 shrink-0 items-center justify-center rounded-full transition-all active:translate-y-px',
            busy || !text.trim()
              ? 'border-line text-ink-faint cursor-not-allowed border'
              : 'bg-accent cursor-pointer text-white hover:opacity-90',
          )}
        >
          <PaperPlaneRightIcon size={16} weight="fill" />
        </button>
      </div>

      <div className="mt-1.5 flex items-center justify-between gap-3">
        <p className="text-ink-faint text-[0.625rem]">{t('inbox.replyHint')}</p>
        {sent && (
          <span className="text-status-ok flex shrink-0 items-center gap-1 text-[0.6875rem]">
            <CheckIcon size={12} weight="bold" />
            {t('inbox.replySent')}
          </span>
        )}
      </div>
      {error && <p className="text-status-fail mt-1.5 text-xs break-all">{error}</p>}
    </div>
  )
}

export function InboxPage({
  initialDate,
  initialMsg,
}: {
  readonly initialDate?: string
  /** `#/inbox?msg=<correlation_id>` — where the Sheet's "Lien audio" cell
   *  lands. The cell used to hold a Drive URL, which opened a bare file with
   *  no transcript, no summary and no reply; this opens the message. */
  readonly initialMsg?: string
}) {
  const { t } = useI18n()
  /*
    Cadence.

    An inbox that only updates when the operator says so is not an inbox, so
    this page does not simply obey `settings.refreshMs` (which can be
    "manual"). It watches instead: while a message is being processed there is
    something worth seeing in a few seconds, and the rest of the time there is
    not. 5 s while anything is in flight, 30 s otherwise.

    The in-flight list itself is polled at the fast rate throughout — it is one
    small query, and it is the thing that decides the other two.
  */
  const flight = useApi('in-flight', api.inFlight, 5000)
  const pending = flight.data?.in_flight ?? []
  const pollMs = pending.length > 0 ? 5000 : 30000
  const reports = useApi('reports', api.reports, pollMs)
  // The messages that never became Sheet rows. Supplementary: the thread must
  // not block on them, so their own failure only silences the archive, never
  // the page.
  const exchanges = useApi('exchanges', api.exchanges, pollMs)

  const [channel, setChannel] = useState<string>('')
  // The selected person; the rail is the picker.
  const [who, setWho] = useState<string>('')
  // Seeded from the deep link out of Overview's year graph (#/inbox?date=…).
  const [date, setDate] = useState<string>(initialDate ?? '')
  // The heatmap is a day picker, not a reading surface. Open when the page was
  // entered without a day already chosen for it.
  const [calendar, setCalendar] = useState(false)

  /*
    One timeline: Sheet rows and logged exchanges, newest first.

    Reports arrive oldest-first and are reversed; exchanges arrive newest-first
    from the API. Merging the two streams without a sort would interleave them
    wrong the moment an exchange is newer than the newest report, so the merged
    list is ordered by (date, heure) descending — the rail's "first occurrence
    is the last message" rule then holds for both kinds alike.
  */
  const all = useMemo<ThreadRow[]>(() => {
    const reports_ = [...(reports.data?.reports ?? [])]
    const exchanges_ = (exchanges.data?.exchanges ?? []).map<ThreadExchange>((e) => ({
      _row: `x${e.id}`,
      id: e.id,
      date: (e.date ?? (e.ts ?? '').slice(0, 10)).trim(),
      heure: (e.heure ?? (e.ts ?? '').slice(11, 16)).trim(),
      canal: e.channel ?? undefined,
      technicien: e.technicien ?? undefined,
      kind: e.kind ?? undefined,
      text: e.text ?? undefined,
      reply: e.reply ?? undefined,
      media_id: e.media_id ?? null,
      stt_engine: e.stt_engine ?? null,
      correlation_id: e.correlation_id ?? null,
    }))
    return [...reports_, ...exchanges_].sort((a, b) => {
      const ka = `${toISODate(a.date) ?? ''} ${a.heure ?? ''}`
      const kb = `${toISODate(b.date) ?? ''} ${b.heure ?? ''}`
      return kb < ka ? -1 : kb > ka ? 1 : 0
    })
  }, [reports.data, exchanges.data])

  /*
    The deep link, resolved.

    The address names a message, not a person or a day, so both filters have to
    be set from whatever row carries that correlation id — and then it must not
    fight the operator: `done` latches, so clicking another day afterwards is
    not undone on the next poll. A correlation id that matches nothing leaves
    the page exactly as it was; the message may simply have been pruned, and
    silently jumping somewhere else would be worse than doing nothing.
  */
  const [target, setTarget] = useState<string>(initialMsg ?? '')
  const seeded = useRef(false)
  useEffect(() => {
    if (seeded.current || !target || all.length === 0) return
    const hit = all.find((r) => (r.correlation_id ?? '').trim() === target)
    if (!hit) return
    seeded.current = true
    setWho((hit.technicien ?? '').trim())
    setDate(toISODate(hit.date) ?? '')
    setCalendar(false)
  }, [all, target])

  const channels = useMemo(
    () => [...new Set(all.map((r) => (r.canal ?? '').trim()).filter(Boolean))],
    [all],
  )

  // Recent people, newest message first. The rail is the conversation list; the
  // channel/date filters narrow it like any list filter.
  const people = useMemo(() => {
    const byName = new Map<
      string,
      { name: string; count: number; last: string; preview: string; channels: Set<string> }
    >()
    for (const r of all) {
      const name = (r.technicien ?? '').trim()
      if (!name) continue
      if (channel && (r.canal ?? '').trim() !== channel) continue
      if (date && toISODate(r.date) !== date) continue
      let p = byName.get(name)
      if (!p) {
        // `all` runs newest-first, so the first occurrence is the last message.
        p = {
          name,
          count: 0,
          last: `${r.date} ${r.heure ?? ''}`.trim(),
          // The last thing said, the way a conversation list shows it — far
          // more use than a raw count when picking who to open. An exchange
          // has no summary, so its own last line stands in.
          preview: ('reply' in r
            ? r.reply || r.text || ''
            : r.resume || r.rapport_complet || ''
          ).trim(),
          channels: new Set(),
        }
        byName.set(name, p)
      }
      p.count += 1
      p.channels.add((r.canal ?? '').trim().toLowerCase())
    }
    return [...byName.values()]
  }, [all, channel, date])

  /*
    The org chart, for two things the Sheet cannot answer.

    The Sheet carries a technician's *name* and nothing else, so "who is this
    person's chef" and "which number did they write from" both have to come from
    `persons`/`technicians`. Same cache key the Équipe page uses, so this costs
    no extra request when the operator has already been there.
  */
  const roster = useApi('technicians', api.technicians)

  /**
   * Names with a message still in the pipeline.
   *
   * Keyed on the name the pipeline logged, which is the same name the Sheet
   * rows carry, so the rail can mark a sender without another lookup.
   */
  const busyNames = useMemo(
    () => new Set(pending.map((f) => (f.technicien ?? '').trim().toLowerCase()).filter(Boolean)),
    [pending],
  )

  /** Lower-cased name → their row on the chart. The Sheet's own join key. */
  const byName = useMemo(() => {
    const m = new Map<string, Technician>()
    for (const p of roster.data?.technicians ?? []) m.set(p.name.trim().toLowerCase(), p)
    return m
  }, [roster.data])

  /**
   * The address a given message arrived on.
   *
   * Matched by channel rather than "their first identity": a person with both a
   * Telegram id and a WhatsApp number would otherwise have every message
   * labelled with whichever one happened to be stored first, which is worse
   * than showing nothing — it is confidently wrong.
   */
  const addressFor = (name: string, canal: string): string | undefined => {
    const chan = canal.trim().toLowerCase()
    const ids = byName.get(name.trim().toLowerCase())?.identities ?? []
    const id = ids.find((i) => i.channel.trim().toLowerCase() === chan)?.external_id
    // A WhatsApp number is stored as 2126… and read as 06… by everyone here.
    return chan === 'whatsapp' ? formatPhone(id) || undefined : id
  }

  /*
    The rail, grouped by chef.

    A flat list of names answers "who wrote" and nothing else. On a site with
    three crews the question is usually "has anyone on Karim's team reported
    today", and a flat list makes that a name-by-name recall exercise against an
    org chart held in the reader's head. Folders put the chart on the screen.

    Someone the roster does not place — a name in the Sheet with no row on the
    chart, or a technician with no chef — lands in a trailing "unassigned"
    group rather than being hidden or silently attached to the first chef. That
    is exactly the case worth seeing: it means a report is not being routed.
  */
  const groups = useMemo(() => {
    const chefName = (name: string): string | null => {
      const person = byName.get(name.trim().toLowerCase())
      if (!person) return null
      if (person.role === 'chef' || person.role === 'directeur') return person.name
      const chef = [...byName.values()].find((p) => p.id === person.manager_id)
      return chef?.name ?? null
    }
    const out = new Map<string, typeof people>()
    for (const p of people) {
      const key = chefName(p.name) ?? ''
      out.set(key, [...(out.get(key) ?? []), p])
    }
    // Named chefs first, alphabetically; the unplaced group always last.
    return [...out.entries()].sort(([a], [b]) => {
      if (a === '') return 1
      if (b === '') return -1
      return a.localeCompare(b)
    })
  }, [people, byName])

  // Falls back to the most recent person when the picker points at someone the
  // current filters removed, so the window never goes stale mid-filter.
  const active = who && people.some((p) => p.name === who) ? who : (people[0]?.name ?? '')

  // The same filter set the rail was counted with, so the badge and the thread
  // always agree.
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

  /**
   * The identity the last message in this thread arrived on.
   *
   * "Their first identity" would label a person who owns both a phone and a
   * Telegram account with whichever was stored first, which is not where the
   * conversation is happening. The newest message knows.
   */
  const preferredIdentity = useMemo(() => {
    const chan = (windowRows[windowRows.length - 1]?.canal ?? windowRows[0]?.canal ?? '')
      .trim()
      .toLowerCase()
    if (!chan) return undefined
    const ids = byName.get(active.trim().toLowerCase())?.identities ?? []
    return ids.find((i) => i.active && i.channel.trim().toLowerCase() === chan)?.id
  }, [windowRows, byName, active])

  const days = useMemo(() => groupByDay(windowRows), [windowRows])
  const dayLabel = useDayLabel()

  const threadRef = useRef<HTMLDivElement | null>(null)

  /*
    Where to land when the thread changes.

    No day picked: the newest message, like every chat client — the thread is
    built oldest-first so the composer sits under the latest exchange, and the
    interesting end would otherwise be the one off-screen.

    A day picked: the *start* of that day. Someone who chose a date is going
    back to read what happened, and reading starts at the beginning; dropping
    them at the last message of the day means scrolling back up through it.
  */
  useEffect(() => {
    const el = threadRef.current
    if (el) el.scrollTop = date ? 0 : el.scrollHeight
  }, [active, days, date])

  /*
    The day the reader is currently inside, as a marker that follows the scroll.

    The separators between days only say what day it is at the moment you pass
    one — scroll a long day and the answer has left the screen. This is the
    floating date chip Telegram and WhatsApp both show: it names the topmost
    day still above the fold, and fades once scrolling stops so it is not a
    permanent label on a surface that is mostly conversation.

    Measured off the section offsets rather than an IntersectionObserver: there
    is one entry per day and the read is a couple of numbers, so an observer
    would be more machinery than the arithmetic it replaces.
  */
  const dayRefs = useRef(new Map<string, HTMLDivElement>())
  const [marker, setMarker] = useState<string | null>(null)

  const readCurrentDay = () => {
    const el = threadRef.current
    if (!el) return
    let current: string | null = null
    for (const [iso, node] of dayRefs.current) {
      if (node.offsetTop - el.scrollTop <= 12) current = iso
    }
    setMarker(current ?? days[0]?.iso ?? null)
  }

  const onThreadScroll = () => readCurrentDay()

  // Seed it after the landing scroll, or the index reads "—" until the first
  // wheel event on a thread the reader has not touched yet.
  useEffect(readCurrentDay, [active, days, date])

  /** Scroll one day's first message to the top of the thread. */
  const jumpToDay = (iso: string) => {
    const el = threadRef.current
    const node = dayRefs.current.get(iso)
    if (el && node) el.scrollTo({ top: node.offsetTop, behavior: 'smooth' })
  }

  if (reports.error) return <ErrorState message={reports.error} onRetry={reports.reload} />
  // First paint only — a later poll never re-shows this, and an exchanges
  // failure still leaves the thread readable (its own `error` is not gated on).
  if (reports.loading || (exchanges.loading && !exchanges.data)) {
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
      /*
        The page is the app: it fills the viewport and hands its overflow to the
        two panes inside. `dvh`, not `vh` — on a phone the address bar is part
        of `vh` and the composer ends up under it.
      */
      className="flex h-[calc(100dvh-7rem)] min-h-[32rem] flex-col gap-3"
    >
      <div className="flex flex-wrap items-center gap-3">
        <Filter
          label={t('inbox.channel')}
          value={channel}
          onChange={setChannel}
          options={channels}
          allLabel={t('inbox.all')}
        />

        {/* The native picker, not a custom one: it is a date field, the browser
            already has a good one per platform, and it is keyboard- and
            screen-reader-correct without any of it being written here. */}
        <label className="text-ink-faint flex items-center gap-2 text-[0.6875rem] tracking-wide uppercase">
          {t('inbox.calendar')}
          <input
            type="date"
            value={date}
            max={todayISO()}
            onChange={(e) => setDate(e.target.value)}
            className="border-line focus:border-accent text-ink bg-canvas tabular cursor-pointer rounded-md border px-2 py-1 text-xs normal-case outline-none transition-colors"
          />
        </label>

        {/* The year heatmap stays as the other way in — it answers "which days
            had anything at all", which a date field cannot. */}
        <button
          type="button"
          onClick={() => setCalendar((v) => !v)}
          aria-expanded={calendar}
          aria-label={t('graph.year')}
          title={t('graph.year')}
          className={cn(
            'border-line flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors',
            calendar ? 'text-ink bg-slate-100 dark:bg-slate-850' : 'text-ink-faint hover:text-ink',
          )}
        >
          <CalendarBlankIcon size={13} />
          <CaretDownIcon
            size={11}
            className={cn('transition-transform', calendar && 'rotate-180')}
          />
        </button>

        {/* Either picker sets the day; this is the only way back to all of them. */}
        {date && (
          <button
            type="button"
            onClick={() => setDate('')}
            className="text-ink-faint hover:text-ink cursor-pointer text-xs underline underline-offset-4"
          >
            {t('inbox.allDays')}
          </button>
        )}

        <span className="tabular text-ink-faint text-xs">{people.length}</span>
      </div>

      {calendar && (
        <div className="border-line bg-surface edge shrink-0 rounded-xl border p-4">
          <ActivityGraphSection
            rows={all}
            date={date || todayISO()}
            onSelectDay={(iso) => {
              setDate(iso)
              setCalendar(false)
            }}
          />
        </div>
      )}

      {people.length === 0 ? (
        <EmptyState body={t('reports.noMatch')} />
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[16rem_minmax(0,1fr)] xl:grid-cols-[16rem_minmax(0,1fr)_11rem]">
          {/* The conversation list: who wrote, what they last said, and when. */}
          <aside className="border-line bg-surface edge hidden min-h-0 flex-col overflow-hidden rounded-xl border lg:flex">
            <h2 className="text-ink-faint border-line shrink-0 border-b px-4 py-2.5 text-[0.6875rem] font-medium tracking-wide uppercase">
              {t('inbox.people')}
            </h2>
            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
              {groups.map(([chef, members]) => (
                <section key={chef || '_'} className="flex flex-col">
                  {/*
                    The folder's own line. Sticky, so the crew you are scrolling
                    through keeps saying whose crew it is — the same reason the
                    thread has a day marker. A label and a rule rather than a
                    nested container: the rail is 16rem wide and a box inside a
                    box would spend a quarter of it on borders.
                  */}
                  <h3 className="border-line bg-surface text-ink-faint sticky top-0 z-10 flex items-center gap-1.5 border-b px-3 py-1.5 text-[0.625rem] font-medium tracking-wide uppercase">
                    {chef ? <UsersThreeIcon size={12} /> : <UserIcon size={12} />}
                    <span className="min-w-0 flex-1 truncate">{chef || t('inbox.unassigned')}</span>
                    <span className="tabular">{members.length}</span>
                  </h3>
                  <ul className="flex flex-col">
                    {members.map((p) => (
                      <li key={p.name}>
                        <button
                          type="button"
                          onClick={() => setWho(p.name)}
                          aria-pressed={active === p.name}
                          className={cn(
                            'flex w-full cursor-pointer flex-col gap-0.5 border-s-2 px-3 py-2.5 text-start transition-colors',
                            active === p.name
                              ? 'border-s-accent bg-accent/5'
                              : 'border-s-transparent hover:bg-slate-100 dark:hover:bg-slate-850',
                          )}
                        >
                          <span className="flex items-baseline gap-2">
                            <span className="text-ink flex min-w-0 flex-1 items-baseline gap-1.5 truncate text-sm font-medium">
                              {p.name}
                              {/* Still being transcribed and extracted. Title,
                                  not colour alone: the state has to survive a
                                  screen reader and a colour-blind reader. */}
                              {busyNames.has(p.name.trim().toLowerCase()) && (
                                <HourglassMediumIcon
                                  size={12}
                                  className="text-accent shrink-0 animate-pulse"
                                  aria-label={t('inbox.processing')}
                                >
                                  <title>{t('inbox.processing')}</title>
                                </HourglassMediumIcon>
                              )}
                            </span>
                            <span className="tabular text-ink-faint shrink-0 text-[0.625rem]">
                              {toISODate(p.last) ?? '—'}
                            </span>
                          </span>
                          <span className="text-ink-faint flex items-center gap-1.5 text-[0.6875rem]">
                            {[...p.channels].map((c) => (
                              <ChannelIcon key={c} channel={c} size={11} />
                            ))}
                            <span className="min-w-0 flex-1 truncate">
                              {p.preview || `${p.count} ${t('inbox.messages')}`}
                            </span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          </aside>

          {/* The conversation itself. */}
          <section className="border-line bg-canvas edge flex min-h-0 flex-col overflow-hidden rounded-xl border">
            <header className="border-line bg-surface flex shrink-0 items-center gap-3 border-b px-4 py-2.5">
              <div className="min-w-0 flex-1">
                <h2 className="text-ink truncate text-sm font-medium">{active}</h2>
                <p className="text-ink-faint mt-0.5 text-[0.6875rem]">
                  {windowRows.length} {t('inbox.messages')}
                </p>
              </div>
              {/* On narrow screens the rail is hidden, so this doubles as the
                  picker rather than the page growing a second layout. */}
              <select
                value={active}
                onChange={(e) => setWho(e.target.value)}
                aria-label={t('inbox.people')}
                className="border-line text-ink bg-canvas cursor-pointer rounded-md border px-2 py-1 text-xs outline-none lg:hidden"
              >
                {people.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.name}
                  </option>
                ))}
              </select>
              {(() => {
                const p = people.find((x) => x.name === active)
                return p ? (
                  <span className="text-ink-faint flex shrink-0 items-center gap-1.5">
                    {[...p.channels].map((c) => (
                      <ChannelIcon key={c} channel={c} size={14} />
                    ))}
                  </span>
                ) : null
              })()}
            </header>

            <div
              ref={threadRef}
              onScroll={onThreadScroll}
              className="thread-canvas flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4"
            >
              {windowRows.length === 0 ? (
                <EmptyState body={t('reports.noMatch')} />
              ) : (
                days.map((d) => (
                  <div
                    key={d.iso}
                    ref={(node) => {
                      // Deleted on unmount, so a day that scrolled out of the
                      // filter cannot go on claiming an offset it no longer has.
                      if (node) dayRefs.current.set(d.iso, node)
                      else dayRefs.current.delete(d.iso)
                    }}
                    className="flex flex-col gap-3"
                  >
                    <DaySeparator iso={d.iso} />
                    {d.rows.map((r) => (
                      <div
                        key={r._row}
                        /* The landing point of a "Lien audio" click. Scrolled
                           to and ringed once, then cleared: a highlight that
                           stayed would read as a status the message does not
                           have. */
                        ref={(node) => {
                          if (node && target && (r.correlation_id ?? '').trim() === target) {
                            node.scrollIntoView({ block: 'center' })
                            // Arriving from the Sheet's "▶ Écouter" cell, so
                            // start the recording rather than making the reader
                            // find the play button they already pressed once.
                            // The element is `preload="none"`, so play() is
                            // what fetches it.
                            //
                            // The catch is not optional and not a swallowed
                            // error: browsers refuse audible playback on a page
                            // the user has not interacted with, and a link from
                            // Google Sheets does not count as interaction. When
                            // it is refused the message is still scrolled to and
                            // ringed with its player under the cursor, which is
                            // the most a page is allowed to do unasked.
                            const audio = node.querySelector('audio')
                            if (audio) void audio.play().catch(() => {})
                            setTarget('')
                          }
                        }}
                        className={cn(
                          'flex flex-col gap-1.5',
                          target &&
                            (r.correlation_id ?? '').trim() === target &&
                            'ring-accent rounded-lg ring-2',
                        )}
                      >
                        {'reply' in r ? (
                          <>
                            <ExchangeIncoming
                              r={r}
                              address={addressFor(r.technicien ?? '', r.canal ?? '')}
                              onSaved={exchanges.reload}
                            />
                            <ExchangeReply r={r} />
                          </>
                        ) : (
                          <>
                            <IncomingBubble
                              r={r}
                              address={addressFor(r.technicien ?? '', r.canal ?? '')}
                              onSaved={reports.reload}
                            />
                            <BotBubble r={r} onSaved={reports.reload} />
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                ))
              )}
            </div>

            <ReplyComposer
              name={active}
              identities={byName.get(active.trim().toLowerCase())?.identities ?? []}
              preferred={preferredIdentity}
            />
          </section>

          {/*
            The day index — the calendar for this conversation.

            The floating chip that used to sit on top of the thread said the
            same thing, but it overlapped the messages it was describing and
            vanished a second after it appeared, so the answer to "where am I"
            was only available while moving. Out here it is permanent, it
            costs the conversation no width, and it can do the other half of
            the job: every day in the thread is listed, the one being read is
            marked, and any of them is one click away.
          */}
          <aside className="border-line bg-surface edge hidden min-h-0 flex-col overflow-hidden rounded-xl border xl:flex">
            <div className="border-line shrink-0 border-b px-3 py-2.5">
              <p className="text-ink-faint text-[0.625rem] tracking-wide uppercase">
                {t('inbox.reading')}
              </p>
              {/* The exact date, always — the written label is friendly but
                  "Mardi 12 août" is not what gets typed into the date field or
                  quoted in a message about a row. */}
              <p className="tabular text-ink mt-0.5 text-sm">{marker ?? '—'}</p>
              <p className="text-ink-faint mt-0.5 text-[0.6875rem] capitalize">
                {marker ? dayLabel(marker) : ''}
              </p>
            </div>

            <h3 className="text-ink-faint border-line shrink-0 border-b px-3 py-1.5 text-[0.625rem] font-medium tracking-wide uppercase">
              {t('inbox.days')}
            </h3>
            <ul className="flex min-h-0 flex-1 flex-col overflow-y-auto py-1">
              {/* Newest first here, oldest first in the thread: this is an index
                  being scanned, not a conversation being read. */}
              {[...days].reverse().map((d) => (
                <li key={d.iso}>
                  <button
                    type="button"
                    onClick={() => jumpToDay(d.iso)}
                    aria-current={marker === d.iso}
                    className={cn(
                      'flex w-full cursor-pointer items-baseline gap-2 border-s-2 px-3 py-1.5 text-start transition-colors',
                      marker === d.iso
                        ? 'border-s-accent bg-accent/5 text-ink'
                        : 'border-s-transparent text-ink-muted hover:bg-slate-100 dark:hover:bg-slate-850',
                    )}
                  >
                    <span className="tabular min-w-0 flex-1 truncate text-xs">{d.iso}</span>
                    <span className="tabular text-ink-faint shrink-0 text-[0.625rem]">
                      {d.rows.length}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>
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
            'cursor-pointer rounded px-2 py-1 text-xs transition-colors',
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
              'cursor-pointer rounded px-2 py-1 text-xs transition-colors',
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
