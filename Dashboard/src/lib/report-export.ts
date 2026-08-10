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
      .replace(/^-/, '')
      .replace(/-$/, '')
      .toLowerCase()
      .slice(0, 60) || 'rapport'
  )
}

/** `data:image/png;base64,iVBO…` -> the bytes, or null if it is not one. */
function bytesOf(dataUri: string): Uint8Array | null {
  const comma = dataUri.indexOf(',')
  if (!dataUri.startsWith('data:') || comma === -1) return null
  const binary = atob(dataUri.slice(comma + 1))
  const out = new Uint8Array(binary.length)
  // atob yields one latin-1 char per byte, so code point === byte value.
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.codePointAt(i) ?? 0
  return out
}

/** The figures printed as a table, so they are not buried in the prose. */
export interface ReportFigures {
  rapports: number
  techniciens: number
  chantiers: number
  flagged: number
  goulottes: number
  cables: number
  bureaux: number
  panneaux: number
}

export interface ReportMeta {
  /** "Rapport journalier" / "Rapport hebdomadaire" — the kind, above the title. */
  kind: string
  /** The date or the date range this covers. */
  period: string
  /** Who asked for it, for the provenance line. */
  author?: string
  figures?: ReportFigures
  /** Name -> what they sent, for the per-technician table. */
  byTech?: { name: string; count: number; goulottes: number; flagged: number }[]
  image?: string | null
}

const INK = '0F172A'
const MUTED = '64748B'
const ACCENT = '2563EB'
const RULE = 'E2E8F0'

/**
 * Writes the report as Word.
 *
 * .docx is the only format. txt and markdown were dropped once the illustrated
 * card became part of the report: a plain-text file cannot carry the picture,
 * so exporting one produced a document quietly missing half of what the
 * operator was looking at.
 *
 * The document is assembled here rather than dumped as paragraphs, because the
 * thing that gets forwarded to a client has to survive being printed: a running
 * header, a figures table, real Word heading styles (so the navigation pane and
 * any later table of contents work), and page numbers in the footer. The model
 * marks its sections with `## `, which is the only markup it is allowed to emit
 * — see `_INSTRUCTIONS` in `api/app/daily_report.py`.
 *
 * The `docx` package builds it — a .docx is a ZIP of XML, which genuinely
 * cannot be hand-rolled — and is imported lazily so its weight only loads when
 * someone actually exports.
 */
export async function exportReport(title: string, body: string, meta: ReportMeta) {
  const d = await import('docx')
  const {
    AlignmentType,
    BorderStyle,
    Document,
    Footer,
    Header,
    HeadingLevel,
    ImageRun,
    Packer,
    PageNumber,
    Paragraph,
    Table,
    TableCell,
    TableRow,
    TextRun,
    WidthType,
  } = d

  const text = (value: string, opts: Record<string, unknown> = {}) =>
    new TextRun({ text: value, font: 'Calibri', ...opts })

  const rule = {
    style: BorderStyle.SINGLE,
    size: 6,
    color: RULE,
  }
  const noBorder = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' }

  /** A label/value pair as one bordered cell — the figures grid. */
  const figureCell = (value: string, label: string) =>
    new TableCell({
      width: { size: 25, type: WidthType.PERCENTAGE },
      margins: { top: 120, bottom: 120, left: 160, right: 160 },
      borders: { top: rule, bottom: rule, left: rule, right: rule },
      children: [
        new Paragraph({
          spacing: { after: 40 },
          children: [text(value, { bold: true, size: 30, color: ACCENT })],
        }),
        new Paragraph({ children: [text(label, { size: 16, color: MUTED, allCaps: true })] }),
      ],
    })

  const cell = (value: string, opts: { bold?: boolean; align?: 'right' } = {}) =>
    new TableCell({
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      borders: { top: noBorder, bottom: rule, left: noBorder, right: noBorder },
      children: [
        new Paragraph({
          alignment: opts.align === 'right' ? AlignmentType.RIGHT : AlignmentType.LEFT,
          children: [
            text(value, { bold: opts.bold, size: 19, color: opts.bold ? INK : '334155' }),
          ],
        }),
      ],
    })

  /**
   * The model's body, turned into Word structure.
   *
   * `## ` becomes a real Heading 2 (not bold text pretending to be one, which
   * is invisible to Word's navigation pane and to a table of contents), and
   * `- ` becomes a genuine list item. Anything else stays a paragraph.
   */
  const bodyBlocks = body
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      if (line.startsWith('## ')) {
        return new Paragraph({
          heading: HeadingLevel.HEADING_2,
          spacing: { before: 320, after: 120 },
          children: [text(line.slice(3), { bold: true, size: 24, color: INK })],
        })
      }
      if (line.startsWith('- ')) {
        return new Paragraph({
          bullet: { level: 0 },
          spacing: { after: 80 },
          children: [text(line.slice(2), { size: 21, color: '334155' })],
        })
      }
      return new Paragraph({
        spacing: { after: 160, line: 300 },
        children: [text(line, { size: 21, color: '334155' })],
      })
    })

  const f = meta.figures
  const figures = f
    ? [
        new Table({
          width: { size: 100, type: WidthType.PERCENTAGE },
          rows: [
            new TableRow({
              children: [
                figureCell(String(f.rapports), 'Rapports'),
                figureCell(String(f.techniciens), 'Techniciens'),
                figureCell(String(f.chantiers), 'Chantiers'),
                figureCell(String(f.flagged), 'À vérifier'),
              ],
            }),
            new TableRow({
              children: [
                figureCell(`${f.goulottes} m`, 'Goulottes'),
                figureCell(`${f.cables} m`, 'Câbles'),
                figureCell(String(f.bureaux), 'Bureaux'),
                figureCell(String(f.panneaux), 'Panneaux'),
              ],
            }),
          ],
        }),
        new Paragraph({ text: '', spacing: { after: 240 } }),
      ]
    : []

  const perTech =
    meta.byTech && meta.byTech.length > 0
      ? [
          new Paragraph({
            heading: HeadingLevel.HEADING_2,
            spacing: { before: 320, after: 120 },
            children: [text('Activité par technicien', { bold: true, size: 24, color: INK })],
          }),
          new Table({
            width: { size: 100, type: WidthType.PERCENTAGE },
            rows: [
              new TableRow({
                tableHeader: true,
                children: [
                  cell('Technicien', { bold: true }),
                  cell('Rapports', { bold: true, align: 'right' }),
                  cell('Goulottes (m)', { bold: true, align: 'right' }),
                  cell('À vérifier', { bold: true, align: 'right' }),
                ],
              }),
              ...meta.byTech.map(
                (row) =>
                  new TableRow({
                    children: [
                      cell(row.name),
                      cell(String(row.count), { align: 'right' }),
                      cell(String(row.goulottes), { align: 'right' }),
                      cell(row.flagged ? String(row.flagged) : '—', { align: 'right' }),
                    ],
                  }),
              ),
            ],
          }),
        ]
      : []

  const bytes = meta.image ? bytesOf(meta.image) : null
  const picture = bytes
    ? [
        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          spacing: { before: 400, after: 120 },
          children: [text('Carte de synthèse', { bold: true, size: 24, color: INK })],
        }),
        new Paragraph({
          // 16:9 at a width that fits A4's text column with default margins.
          children: [
            new ImageRun({ data: bytes, transformation: { width: 600, height: 338 }, type: 'png' }),
          ],
        }),
      ]
    : []

  const doc = new Document({
    creator: 'aznet',
    title,
    description: `${meta.kind} · ${meta.period}`,
    styles: {
      default: {
        document: { run: { font: 'Calibri', size: 21, color: '334155' } },
      },
    },
    sections: [
      {
        properties: { page: { margin: { top: 1000, bottom: 1000, left: 1000, right: 1000 } } },
        headers: {
          default: new Header({
            children: [
              new Paragraph({
                border: { bottom: rule },
                spacing: { after: 240 },
                children: [
                  text('AZNET', { bold: true, size: 18, color: ACCENT, characterSpacing: 30 }),
                  text('   ·   ', { size: 18, color: RULE }),
                  text(meta.kind, { size: 18, color: MUTED, allCaps: true }),
                ],
              }),
            ],
          }),
        },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                alignment: AlignmentType.RIGHT,
                border: { top: rule },
                spacing: { before: 120 },
                children: [
                  text(`${meta.period}   `, { size: 16, color: MUTED }),
                  new TextRun({
                    children: [PageNumber.CURRENT, ' / ', PageNumber.TOTAL_PAGES],
                    font: 'Calibri',
                    size: 16,
                    color: MUTED,
                  }),
                ],
              }),
            ],
          }),
        },
        children: [
          new Paragraph({
            heading: HeadingLevel.TITLE,
            spacing: { after: 60 },
            children: [text(title, { bold: true, size: 40, color: INK })],
          }),
          new Paragraph({
            spacing: { after: 320 },
            children: [
              text(
                meta.author && meta.author !== 'automatique'
                  ? `${meta.period} · établi par ${meta.author}`
                  : `${meta.period} · rapport automatique`,
                { size: 18, color: MUTED },
              ),
            ],
          }),
          ...figures,
          ...bodyBlocks,
          ...perTech,
          ...picture,
        ],
      },
    ],
  })

  download(await Packer.toBlob(doc), `${slug(title)}.docx`)
}
