export const FORMATS = ['txt', 'markdown', 'docx'] as const
export type ReportFormat = (typeof FORMATS)[number]

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  // Revoking immediately can cancel the download in Safari; one tick is enough.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** `Rapport journalier — 2026-07-25` -> `rapport-journalier-2026-07-25` */
function slug(title: string) {
  return (
    title
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .replace(/[^a-zA-Z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .toLowerCase()
      .slice(0, 60) || 'rapport'
  )
}

/**
 * Writes the report in the operator's chosen format.
 *
 * txt and markdown are plain strings. docx is a ZIP of XML, which genuinely
 * cannot be hand-rolled, so the `docx` package builds it — lazily imported so
 * its weight only loads when someone actually exports Word.
 */
export async function exportReport(title: string, body: string, format: ReportFormat) {
  const name = slug(title)

  if (format === 'txt') {
    download(new Blob([`${title}\n\n${body}`], { type: 'text/plain;charset=utf-8' }), `${name}.txt`)
    return
  }

  if (format === 'markdown') {
    const md = `# ${title}\n\n${body
      .split(/\n{2,}/)
      .map((p) => p.trim())
      .filter(Boolean)
      .join('\n\n')}\n`
    download(new Blob([md], { type: 'text/markdown;charset=utf-8' }), `${name}.md`)
    return
  }

  const { Document, Packer, Paragraph, HeadingLevel } = await import('docx')
  const doc = new Document({
    sections: [
      {
        children: [
          new Paragraph({ text: title, heading: HeadingLevel.HEADING_1 }),
          // One paragraph per blank-line-separated block: the model writes prose,
          // and collapsing it into a single run would lose its structure.
          ...body
            .split(/\n{2,}/)
            .map((p) => p.trim())
            .filter(Boolean)
            .map((p) => new Paragraph({ text: p, spacing: { after: 200 } })),
        ],
      },
    ],
  })
  download(await Packer.toBlob(doc), `${name}.docx`)
}
