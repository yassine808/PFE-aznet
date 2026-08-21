import {
  DownloadSimpleIcon,
  FileDashedIcon,
  FileDocIcon,
  PencilSimpleIcon,
} from '@phosphor-icons/react'
import {
  api,
  periodDocxUrl,
  reportVersionDocxUrl,
  reportVersions,
  useApi,
  type ReportVersion,
} from '@/lib/api'
import { DocxView } from '@/components/docx-view'
import { useI18n } from '@/lib/i18n'
import { Skeleton } from '@/components/states'

/**
 * The last document generated for a period, standing on its own.
 *
 * The editor carries a preview of its own, but only once somebody has pressed
 * Générer in this browser tab — so the page a manager opens in the morning
 * showed aggregates it had computed itself and no trace of the report the
 * 18:00 job had already written and mailed. This reads the stored versions
 * directly, which means the answer to "what went out for this day" is on the
 * page before any button is touched.
 *
 * A period with no report at all still renders — one line saying so. Rendering
 * nothing was the first shape and it was wrong: an absence looks exactly like a
 * feature that failed to load, and "today has no report yet" is a fact the page
 * should state rather than leave the reader to infer from blank space.
 */
export function LastReportDocx({
  kind,
  period,
  managerId = -1,
  reloadToken = 0,
  editHref,
}: {
  readonly kind: 'daily' | 'weekly'
  readonly period: string
  /** Whose versions to look at. -1, the default, means "whoever wrote it":
   *  this panel answers "what document went out for this period", and that has
   *  one answer whether the scheduler, a chef or a director produced it. */
  readonly managerId?: number
  /** Bumped by the page after Générer. It is part of the cache key, so a run
   *  that just stored a new version replaces the document on screen instead of
   *  leaving the button looking like it did nothing. */
  readonly reloadToken?: number
  /** Where correcting this report happens. Daily and Weekly only show the
   *  document now, so without this the way to fix a wrong figure is to know
   *  that the Reports page exists and to find the same report in its list. */
  readonly editHref?: string
}) {
  const { t } = useI18n()
  // The index without bodies: this panel needs one id and one label, and the
  // documents themselves are fetched one at a time by the viewer.
  const history = useApi(`last-docx:${kind}:${period}:${managerId}:${reloadToken}`, (s) =>
    reportVersions(kind, period, false, s, managerId),
  )
  // The stored reports, for the periods that have a text but no file: every
  // report generated before the document column existed, and any whose render
  // failed at the time. Without this the page of every past day would show
  // nothing and read as broken while the report itself existed all along.
  const generated = useApi(`reports/generated:${reloadToken}`, api.generatedReports)

  if ((history.loading && !history.data) || (generated.loading && !generated.data))
    return <Skeleton className="h-72 rounded-xl" />

  const version: ReportVersion | undefined = (history.data?.versions ?? []).find((v) => v.has_docx)
  const stored = (generated.data?.reports ?? []).find(
    (g) => g.period === period && (g.period_type === 'weekly') === (kind === 'weekly'),
  )
  if (!version && !stored) {
    return (
      <section className="border-line text-ink-faint flex items-center gap-2.5 rounded-xl border border-dashed px-5 py-6 text-xs">
        <FileDashedIcon size={15} className="shrink-0" />
        {t('editor.docxNone')}
      </section>
    )
  }

  const src = version ? reportVersionDocxUrl(version.id) : periodDocxUrl(kind, period)
  const label = version
    ? t('editor.docxOf', { version: version.version, author: version.author })
    : t('editor.docxLast', { author: stored?.generated_by ?? '' })

  return (
    <section className="border-line bg-surface edge flex flex-col gap-3 rounded-xl border p-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-ink-faint flex items-center gap-2 text-[0.6875rem] font-medium tracking-wide uppercase">
          <FileDocIcon size={13} />
          {label}
        </h2>
        <div className="ms-auto flex flex-wrap items-center gap-2">
          {editHref && (
            <a
              href={editHref}
              className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2"
            >
              <PencilSimpleIcon size={13} />
              {t('editor.edit')}
            </a>
          )}
          <a
            href={version ? reportVersionDocxUrl(version.id, true) : src}
            download
            className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2"
          >
            <DownloadSimpleIcon size={13} />
            {t('editor.downloadDocx')}
          </a>
        </div>
      </div>
      <DocxView src={src} />
    </section>
  )
}
