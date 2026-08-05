import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  ArrowCounterClockwiseIcon,
  CheckIcon,
  ClockCounterClockwiseIcon,
  DownloadSimpleIcon,
  FloppyDiskIcon,
  PencilSimpleIcon,
} from '@phosphor-icons/react'
import { reportVersions, saveReportVersion, useApi, type ReportVersion } from '@/lib/api'
import { diffCounts, diffLines } from '@/lib/diff'
import { useI18n } from '@/lib/i18n'
import { exportReport, type ReportFigures } from '@/lib/report-export'
import { cn } from '@/lib/utils'

/**
 * The report, editable, with its own history.
 *
 * The model writes a first draft and a manager corrects it: a site name it
 * misheard, a sentence too blunt to send to a client. Before this, correcting
 * meant copying the text into Word — at which point the dashboard's copy and
 * the sent document silently disagreed forever.
 *
 * Three rules the shape follows:
 *
 * - **Saving appends, never overwrites.** The model's own wording is evidence
 *   of what the pipeline produced; an edit that replaces it destroys the only
 *   record of what was actually extracted.
 * - **The diff is derived, never stored.** It is a pure function of the draft
 *   and the last saved version, so it cannot go stale the way a cached
 *   "modified" flag does.
 * - **Export is one format.** .docx, with the generated card embedded — see
 *   `lib/report-export.ts` for why txt and markdown were dropped.
 */
export function ReportEditor({
  kind,
  period,
  objet,
  corps,
  image,
  generatedBy,
  figures,
  byTech,
}: {
  readonly kind: 'daily' | 'weekly'
  readonly period: string
  readonly objet: string
  readonly corps: string
  /** The illustrated card, if one has been generated on this page. */
  readonly image?: string | null
  readonly generatedBy?: string
  /** The page's own aggregates, printed as a table in the .docx. */
  readonly figures?: ReportFigures
  readonly byTech?: { name: string; count: number; goulottes: number; flagged: number }[]
}) {
  const { t } = useI18n()
  const history = useApi(`report-versions:${kind}:${period}`, (s) => reportVersions(kind, period, true, s))

  const [draft, setDraft] = useState(corps)
  const [title, setTitle] = useState(objet)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [openVersion, setOpenVersion] = useState<ReportVersion | null>(null)

  // A freshly generated report replaces the buffer — but only when the model's
  // text itself changes. Keying on `corps` rather than on mount is what lets
  // "regenerate" reach the editor while an operator switching days does not
  // silently lose what they were typing.
  useEffect(() => {
    setDraft(corps)
    setTitle(objet)
    setSaved(false)
  }, [corps, objet])

  const versions = history.data?.versions ?? []
  const latest = versions[0] ?? null
  // Compared against the last save when there is one, and against the model's
  // own text when there is not: the first edit of the day should still show
  // what it changed.
  const baseline = latest?.corps ?? corps
  const lines = useMemo(() => diffLines(baseline, draft), [baseline, draft])
  const counts = useMemo(() => diffCounts(lines), [lines])
  const dirty = counts.added > 0 || counts.removed > 0 || title !== (latest?.objet ?? objet)

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      await saveReportVersion({ kind, period, objet: title, corps: draft, image })
      history.reload()
      setSaved(true)
      setEditing(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="border-line bg-surface edge rounded-xl border p-6"
    >
      <div className="border-line flex flex-wrap items-start justify-between gap-4 border-b pb-4">
        <div className="min-w-0 flex-1">
          <p className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
            {t('daily.subject')}
          </p>
          {editing ? (
            <label className="mt-1 block">
              <span className="sr-only">{t('daily.subject')}</span>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="border-line focus:border-accent focus-visible:ring-accent text-ink bg-canvas w-full rounded-md border px-3 py-1.5 text-lg font-medium tracking-tight outline-none transition-colors focus-visible:ring-2"
              />
            </label>
          ) : (
            <h2 className="text-ink mt-1 text-lg font-medium tracking-tight">{title}</h2>
          )}
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setEditing((v) => !v)}
            aria-pressed={editing}
            className={cn(
              'focus-visible:ring-accent flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2 active:translate-y-px',
              editing
                ? 'border-accent text-accent'
                : 'border-line text-ink-muted hover:text-ink',
            )}
          >
            <PencilSimpleIcon size={13} />
            {editing ? t('editor.preview') : t('editor.edit')}
          </button>

          <button
            type="button"
            onClick={save}
            disabled={busy || !dirty}
            className={cn(
              'focus-visible:ring-accent flex items-center gap-2 rounded-md px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2 active:translate-y-px',
              busy || !dirty
                ? 'border-line text-ink-faint cursor-not-allowed border'
                : 'bg-accent cursor-pointer text-white',
            )}
          >
            {saved && !dirty ? <CheckIcon size={13} /> : <FloppyDiskIcon size={13} />}
            {busy ? t('editor.saving') : saved && !dirty ? t('editor.saved') : t('editor.save')}
          </button>

          <button
            type="button"
            onClick={() =>
              void exportReport(title, draft, {
                kind: t(kind === 'daily' ? 'editor.kindDaily' : 'editor.kindWeekly'),
                period,
                author: generatedBy,
                figures,
                byTech,
                image,
              })
            }
            className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2 active:translate-y-px"
          >
            <DownloadSimpleIcon size={13} />
            {t('editor.exportDocx')}
          </button>
        </div>
      </div>

      {/* Errors are announced, not merely coloured — a save that failed while
          the operator was looking at the text must reach a screen reader too. */}
      {error && (
        <p role="alert" className="text-status-fail mt-3 text-xs break-all">
          {error}
        </p>
      )}

      <p className="text-ink-faint mt-3 text-xs">
        {generatedBy && generatedBy !== 'automatique'
          ? t('daily.generatedBy', { name: generatedBy })
          : t('daily.generatedAuto')}
        {latest && ` · ${t('editor.lastSaved', { version: latest.version, author: latest.author })}`}
      </p>

      <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,1fr)_15rem]">
        <div className="min-w-0 flex flex-col gap-4">
          {editing ? (
            <label className="flex flex-col gap-1.5">
              <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
                {t('editor.body')}
              </span>
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={16}
                spellCheck
                className="border-line focus:border-accent focus-visible:ring-accent text-ink bg-canvas min-h-64 w-full resize-y rounded-md border px-3 py-2.5 text-sm leading-relaxed outline-none transition-colors focus-visible:ring-2"
              />
            </label>
          ) : (
            <DiffView lines={lines} />
          )}

          {image && (
            <figure className="flex flex-col gap-2">
              <img
                src={image}
                alt={title}
                className="border-line max-h-72 w-auto rounded-lg border"
              />
              <figcaption className="text-ink-faint text-xs">{t('editor.imageInDoc')}</figcaption>
            </figure>
          )}
        </div>

        <VersionList
          versions={versions}
          counts={counts}
          dirty={dirty}
          onOpen={setOpenVersion}
          onRestore={(v) => {
            setDraft(v.corps ?? '')
            setTitle(v.objet)
            setEditing(true)
          }}
        />
      </div>

      <AnimatePresence>
        {openVersion && (
          <VersionModal version={openVersion} onClose={() => setOpenVersion(null)} />
        )}
      </AnimatePresence>
    </motion.article>
  )
}

/**
 * The body with a change gutter, the way a diff reads on GitHub.
 *
 * Every line carries a sign (+ / − / ·) as well as its tint, because the tints
 * available here are two weights of one accent — the status band is reserved
 * for pipeline state — and a change you can only see by hue is a change a
 * colour-blind operator cannot see at all.
 */
function DiffView({ lines }: { readonly lines: ReturnType<typeof diffLines> }) {
  const { t } = useI18n()
  const changed = lines.some((l) => l.kind !== 'same')

  // Nothing changed since the last save, so show the document itself rather
  // than a diff of one column against itself.
  if (!changed) return <Prose text={lines.map((l) => l.text).join('\n')} />

  return (
    <div className="border-line overflow-hidden rounded-md border">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{t('editor.diffCaption')}</caption>
        <tbody>
          {lines.map((l, i) => (
            <tr
              key={`${i}-${l.kind}`}
              className={cn(
                l.kind === 'added' && 'bg-accent/10',
                l.kind === 'removed' && 'bg-accent-400/10',
              )}
            >
              <td className="text-ink-faint tabular w-10 select-none border-e border-line px-2 py-1 text-end align-top text-[0.6875rem]">
                {l.line ?? ''}
              </td>
              <td
                className={cn(
                  'w-6 select-none px-2 py-1 text-center align-top font-medium',
                  l.kind === 'added' && 'text-accent',
                  l.kind === 'removed' && 'text-ink-faint',
                )}
                aria-label={t(
                  l.kind === 'added'
                    ? 'editor.lineAdded'
                    : l.kind === 'removed'
                      ? 'editor.lineRemoved'
                      : 'editor.lineSame',
                )}
              >
                {l.kind === 'added' ? '+' : l.kind === 'removed' ? '−' : ''}
              </td>
              <td
                className={cn(
                  'px-2 py-1 leading-relaxed whitespace-pre-wrap',
                  l.kind === 'removed' ? 'text-ink-faint line-through' : 'text-ink',
                )}
              >
                {l.text || ' '}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * The report as it will read in Word.
 *
 * The model marks sections with `## ` and items with `- ` and is allowed no
 * other markup, so this is a five-line renderer rather than a Markdown
 * dependency — and showing the same three levels the .docx uses means the
 * preview is a preview, not a different document that happens to share text.
 */
function Prose({ text }: { readonly text: string }) {
  const blocks = text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

  return (
    <div className="flex max-w-[70ch] flex-col gap-1">
      {blocks.map((line, i) => {
        if (line.startsWith('## ')) {
          return (
            <h3
              key={i}
              className="text-ink-faint border-line mt-4 border-b pb-1.5 text-[0.6875rem] font-medium tracking-wide uppercase first:mt-0"
            >
              {line.slice(3)}
            </h3>
          )
        }
        if (line.startsWith('- ')) {
          return (
            <p key={i} className="text-ink flex gap-2 text-sm leading-relaxed">
              <span className="bg-accent mt-2 size-1 shrink-0 rounded-full" aria-hidden="true" />
              <span>{line.slice(2)}</span>
            </p>
          )
        }
        return (
          <p key={i} className="text-ink text-sm leading-relaxed">
            {line}
          </p>
        )
      })}
    </div>
  )
}

/** Saves, newest first, with what is currently unsaved pinned above them. */
function VersionList({
  versions,
  counts,
  dirty,
  onOpen,
  onRestore,
}: {
  readonly versions: ReportVersion[]
  readonly counts: { added: number; removed: number }
  readonly dirty: boolean
  readonly onOpen: (v: ReportVersion) => void
  readonly onRestore: (v: ReportVersion) => void
}) {
  const { t } = useI18n()
  return (
    <aside className="flex flex-col gap-3">
      <h3 className="text-ink-faint flex items-center gap-2 text-[0.6875rem] tracking-wide uppercase">
        <ClockCounterClockwiseIcon size={13} />
        {t('editor.history')}
      </h3>

      <p
        className={cn(
          'border-line rounded-md border border-dashed px-3 py-2 text-xs',
          dirty ? 'text-ink' : 'text-ink-faint',
        )}
      >
        {dirty ? (
          <>
            {t('editor.unsaved')}{' '}
            <span className="text-accent tabular">+{counts.added}</span>{' '}
            <span className="tabular">−{counts.removed}</span>
          </>
        ) : (
          t('editor.upToDate')
        )}
      </p>

      {versions.length === 0 ? (
        <p className="text-ink-faint text-xs italic">{t('editor.noVersions')}</p>
      ) : (
        <ul className="divide-line flex flex-col divide-y">
          {versions.map((v) => (
            <li key={v.id} className="flex items-center gap-2 py-2">
              <button
                type="button"
                onClick={() => onOpen(v)}
                className="focus-visible:ring-accent min-w-0 flex-1 cursor-pointer rounded text-start outline-none focus-visible:ring-2"
              >
                <span className="text-ink tabular text-xs">v{v.version}</span>
                <span className="text-ink-faint ms-2 text-xs">{v.author}</span>
                <span className="text-ink-faint block truncate text-[0.6875rem]">
                  {v.created_at.slice(0, 16).replace('T', ' ')}
                </span>
              </button>
              <button
                type="button"
                onClick={() => onRestore(v)}
                aria-label={t('editor.restoreOne', { version: v.version })}
                className="text-ink-faint hover:text-ink focus-visible:ring-accent cursor-pointer rounded p-1 transition-colors outline-none focus-visible:ring-2"
              >
                <ArrowCounterClockwiseIcon size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}

/** One old version, read-only, in a modal that can be dismissed with Esc. */
function VersionModal({
  version,
  onClose,
}: {
  readonly version: ReportVersion
  readonly onClose: () => void
}) {
  const { t } = useI18n()
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => ref.current?.showModal(), [])

  return (
    <dialog
      ref={ref}
      onCancel={onClose}
      onClose={onClose}
      aria-label={`v${version.version} — ${version.objet}`}
      className="bg-panel border-line text-ink m-auto max-h-[80vh] w-[min(46rem,90vw)] overflow-y-auto rounded-xl border p-6 shadow-lg backdrop:bg-slate-950/40 backdrop:backdrop-blur-sm"
    >
      <div className="border-line flex items-start justify-between gap-4 border-b pb-3">
        <div>
          <p className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
            v{version.version} · {version.author}
          </p>
          <h2 className="text-ink mt-1 text-base font-medium">{version.objet}</h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent cursor-pointer rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2"
        >
          {t('nav.close')}
        </button>
      </div>
      <p className="text-ink mt-4 max-w-[70ch] text-sm leading-relaxed whitespace-pre-wrap">
        {version.corps}
      </p>
      {version.image && (
        <img
          src={version.image}
          alt={version.objet}
          className="border-line mt-4 max-h-72 w-auto rounded-lg border"
        />
      )}
    </dialog>
  )
}
