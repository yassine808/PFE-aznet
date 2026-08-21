import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  ArrowCounterClockwiseIcon,
  CheckIcon,
  ClockCounterClockwiseIcon,
  DownloadSimpleIcon,
  FileDocIcon,
  FloppyDiskIcon,
  PencilSimpleIcon,
} from '@phosphor-icons/react'
import {
  reportVersionDocxUrl,
  reportVersions,
  saveReportVersion,
  useApi,
  type ReportVersion,
} from '@/lib/api'
import { DocxView } from '@/components/docx-view'
import { diffCounts, diffLines } from '@/lib/diff'
import { useI18n } from '@/lib/i18n'
import { exportReport } from '@/lib/report-export'
import { useToast } from '@/lib/toast'
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
 * - **Export is one format.** .docx — see `lib/report-export.ts` for why txt
 *   and markdown were dropped.
 */
export function ReportEditor({
  kind,
  period,
  objet,
  corps,
  generatedBy,
  managerId = 0,
  showDocument = true,
}: {
  readonly kind: 'daily' | 'weekly'
  readonly period: string
  readonly objet: string
  readonly corps: string
  readonly generatedBy?: string
  /** Whose report this is: 0 for the company-wide one, a person id for a
   *  chef's. It keys the history, so the Reports page can edit one chef's
   *  report without appending into another's. */
  readonly managerId?: number
  /** Whether to render the document under the text. False where the page shows
   *  it already — the Reports pane puts the document first, and the same file
   *  twice on one screen is a file the reader has to check against itself. */
  readonly showDocument?: boolean
}) {
  const { t } = useI18n()
  const toast = useToast()
  const history = useApi(`report-versions:${kind}:${period}:${managerId}`, (s) =>
    reportVersions(kind, period, true, s, managerId),
  )

  const [draft, setDraft] = useState(corps)
  const [title, setTitle] = useState(objet)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [openVersion, setOpenVersion] = useState<ReportVersion | null>(null)
  // Which stored document the panel below shows. null means "the newest one
  // that has one" — a page opened cold should already be showing the last
  // generated .docx, not an empty frame with a picker.
  const [shownDocx, setShownDocx] = useState<number | null>(null)

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
  const docxVersion =
    versions.find((v) => v.id === shownDocx) ?? versions.find((v) => v.has_docx) ?? null
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
      await saveReportVersion({ kind, period, objet: title, corps: draft, manager_id: managerId })
      history.reload()
      setSaved(true)
      setEditing(false)
      toast({ tone: 'success', title: t('editor.saved'), body: `${kind} · ${period}` })
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
      // Both, on purpose: the inline error is the record of what went wrong and
      // stays until it is fixed; the toast is what makes it noticed when the
      // save button is off-screen at the bottom of a long report.
      toast({ tone: 'error', title: t('editor.saveFailed'), body: message })
    } finally {
      setBusy(false)
    }
  }

  let saveLabelKey = 'editor.save'
  if (busy) saveLabelKey = 'editor.saving'
  else if (saved && !dirty) saveLabelKey = 'editor.saved'

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
            {t(saveLabelKey)}
          </button>

          <button
            type="button"
            onClick={() => {
              // The document is rendered by the API now, so this can fail the
              // way any request can — the old in-browser build could not, and
              // a silent no-op on a button labelled "Export" is worse than a
              // message saying why nothing downloaded.
              setError(null)
              void exportReport(title, draft, {
                kind: t(kind === 'daily' ? 'editor.kindDaily' : 'editor.kindWeekly'),
                period,
                author: generatedBy,
              }).catch((err: unknown) =>
                setError(err instanceof Error ? err.message : String(err)),
              )
            }}
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
        </div>

        <VersionList
          versions={versions}
          counts={counts}
          dirty={dirty}
          shownDocx={docxVersion?.id ?? null}
          onShowDocx={setShownDocx}
          onOpen={setOpenVersion}
          onRestore={(v) => {
            setDraft(v.corps ?? '')
            setTitle(v.objet)
            setEditing(true)
          }}
        />
      </div>

      {showDocument && <DocxPanel version={docxVersion} />}

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
type DiffKind = ReturnType<typeof diffLines>[number]['kind']

const DIFF_SIGN: Record<DiffKind, string> = { added: '+', removed: '−', same: '' }
const DIFF_LABEL: Record<DiffKind, string> = {
  added: 'editor.lineAdded',
  removed: 'editor.lineRemoved',
  same: 'editor.lineSame',
}

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
                aria-label={t(DIFF_LABEL[l.kind])}
              >
                {DIFF_SIGN[l.kind]}
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
        // Two identical lines are legal prose, so the index has to stay in the
        // key — pairing it with the text keeps it stable when a line is edited.
        const key = `${i}-${line.slice(0, 24)}`
        if (line.startsWith('## ')) {
          return (
            <h3
              key={key}
              className="text-ink-faint border-line mt-4 border-b pb-1.5 text-[0.6875rem] font-medium tracking-wide uppercase first:mt-0"
            >
              {line.slice(3)}
            </h3>
          )
        }
        if (line.startsWith('- ')) {
          return (
            <p key={key} className="text-ink flex gap-2 text-sm leading-relaxed">
              <span className="bg-accent mt-2 size-1 shrink-0 rounded-full" aria-hidden="true" />
              <span>{line.slice(2)}</span>
            </p>
          )
        }
        return (
          <p key={key} className="text-ink text-sm leading-relaxed">
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
  shownDocx,
  onShowDocx,
  onOpen,
  onRestore,
}: {
  readonly versions: ReportVersion[]
  readonly counts: { added: number; removed: number }
  readonly dirty: boolean
  readonly shownDocx: number | null
  readonly onShowDocx: (id: number) => void
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
              {v.has_docx && (
                <button
                  type="button"
                  onClick={() => onShowDocx(v.id)}
                  aria-pressed={shownDocx === v.id}
                  aria-label={t('editor.showDocx', { version: v.version })}
                  className={cn(
                    'focus-visible:ring-accent cursor-pointer rounded p-1 transition-colors outline-none focus-visible:ring-2',
                    shownDocx === v.id ? 'text-accent' : 'text-ink-faint hover:text-ink',
                  )}
                >
                  <FileDocIcon size={13} />
                </button>
              )}
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
  // Guarded: StrictMode double-invokes this effect in dev, and a second
  // showModal() on an already-open dialog throws InvalidStateError.
  useEffect(() => {
    if (ref.current && !ref.current.open) ref.current.showModal()
  }, [])

  return (
    <dialog
      ref={ref}
      onCancel={onClose}
      onClose={onClose}
      aria-label={`v${version.version} — ${version.objet}`}
      className="bg-surface border-line text-ink m-auto max-h-[80vh] w-[min(46rem,90vw)] overflow-y-auto rounded-xl border p-6 shadow-lg backdrop:bg-slate-950/40 backdrop:backdrop-blur-sm"
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
    </dialog>
  )
}

/**
 * The document, below the text it came from.
 *
 * A report is read in the dashboard and *sent* as a .docx, and until this panel
 * the two were only claimed to be the same file — the operator saw a styled
 * paragraph and the director opened a Word document with tables, flags and a
 * provenance line nobody had ever previewed. These are the stored bytes of the
 * version named in the header, so what is on screen is literally what was sent.
 *
 * Nothing is rendered at all when no version carries a document: an empty
 * frame under a report reads as a broken preview, while its absence plus the
 * Export button above reads as "not generated yet", which is the truth.
 */
function DocxPanel({ version }: { readonly version: ReportVersion | null }) {
  const { t } = useI18n()
  if (!version?.has_docx) return null

  return (
    <section className="border-line mt-6 flex flex-col gap-3 border-t pt-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-ink-faint flex items-center gap-2 text-[0.6875rem] tracking-wide uppercase">
          <FileDocIcon size={13} />
          {t('editor.docxOf', { version: version.version, author: version.author })}
        </h3>
        {/* A plain link, not a fetch-and-blob: the API already answers this URL
            with a download disposition, and the browser's own downloader
            handles a large file better than anything built here would. */}
        <a
          href={reportVersionDocxUrl(version.id, true)}
          download
          className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2"
        >
          <DownloadSimpleIcon size={13} />
          {t('editor.downloadDocx')}
        </a>
      </div>
      <DocxView src={reportVersionDocxUrl(version.id)} />
    </section>
  )
}
