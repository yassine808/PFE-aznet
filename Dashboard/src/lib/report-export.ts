import { BASE, fail } from '@/lib/api'

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  // Revoking immediately can cancel the download in Safari; one tick is enough.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** `attachment; filename="rapport-…docx"` → `rapport-…docx`. */
function nameFrom(header: string | null, fallback: string): string {
  const match = /filename="?([^";]+)"?/.exec(header ?? '')
  return match?.[1] ?? fallback
}

export interface ReportMeta {
  /** "Rapport journalier" / "Rapport hebdomadaire" — kept for the caller's own
   *  labelling; the document's own header is chosen by the API from `period`. */
  kind: string
  /** The day (`2026-08-16`) or the range (`2026-08-10 → 2026-08-16`). */
  period: string
  /** Who asked for it, for the provenance line. */
  author?: string
}

/**
 * Downloads the report as Word.
 *
 * The document itself is built by the API (`api/app/docx_report.py`), not here.
 * It used to be assembled in this file with the `docx` package, which meant the
 * scheduled mail — sent by `jobs.py` from a thread inside the container, with
 * no browser anywhere — could not attach one: the document existed only if a
 * human clicked this button, which is the opposite of what a scheduled report
 * is for. The owner's decision (2026-08-16) is one renderer in the backend; the
 * button downloads those same bytes so what a director receives by mail and
 * what an operator exports by hand cannot drift apart.
 *
 * The figures and the per-technician table are *not* sent: the API recomputes
 * them from the Sheet rows the period covers. The body is, because the operator
 * may have edited the draft — that edited text is the report.
 */
export async function exportReport(title: string, body: string, meta: ReportMeta) {
  const res = await fetch(`${BASE}/reports/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, body, period: meta.period, author: meta.author }),
  })
  if (!res.ok) await fail(res)
  download(await res.blob(), nameFrom(res.headers.get('Content-Disposition'), 'rapport.docx'))
}
