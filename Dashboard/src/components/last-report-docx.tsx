import { DownloadSimpleIcon, FileDocIcon } from '@phosphor-icons/react'
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
 * Nothing renders when no version carries a document: an empty frame reads as
 * a broken preview, while its absence next to the Générer button reads as "not
 * generated yet", which is the truth.
 */
export function LastReportDocx({
  kind,
  period,
  managerId = -1,
}: {
  readonly kind: 'daily' | 'weekly'
  readonly period: string
  /** Whose versions to look at. -1, the default, means "whoever wrote it":
   *  this panel answers "what document went out for this period", and that has
   *  one answer whether the scheduler, a chef or a director produced it. */
  readonly managerId?: number
}) {
  const { t } = useI18n()
  // The index without bodies: this panel needs one id and one label, and the
  // documents themselves are fetched one at a time by the viewer.
  const history = useApi(`last-docx:${kind}:${period}:${managerId}`, (s) =>
    reportVersions(kind, period, false, s, managerId),
  )
  // The stored reports, for the periods that have a text but no file: every
  // report generated before the document column existed, and any whose render
  // failed at the time. Without this the page of every past day would show
  // nothing and read as broken while the report itself existed all along.
  const generated = useApi('reports/generated', api.generatedReports)

  if ((history.loading && !history.data) || (generated.loading && !generated.data))
    return <Skeleton className="h-72 rounded-xl" />

  const version: ReportVersion | undefined = (history.data?.versions ?? []).find((v) => v.has_docx)
  const stored = (generated.data?.reports ?? []).find(
    (g) => g.period === period && (g.period_type === 'weekly') === (kind === 'weekly'),
  )
  if (!version && !stored) return null

  const src = version ? reportVersionDocxUrl(version.id) : periodDocxUrl(kind, period)
  const label = version
    ? t('editor.docxOf', { version: version.version, author: version.author })
    : t('editor.docxLast', { author: stored?.generated_by ?? '' })

  return (
    <section className="border-line bg-surface edge flex flex-col gap-3 rounded-xl border p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-ink-faint flex items-center gap-2 text-[0.6875rem] font-medium tracking-wide uppercase">
          <FileDocIcon size={13} />
          {label}
        </h2>
        <a
          href={version ? reportVersionDocxUrl(version.id, true) : src}
          download
          className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2"
        >
          <DownloadSimpleIcon size={13} />
          {t('editor.downloadDocx')}
        </a>
      </div>
      <DocxView src={src} />
    </section>
  )
}
