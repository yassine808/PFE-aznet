import { useEffect, useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { ArrowUUpLeftIcon, FileTextIcon } from '@phosphor-icons/react'
import {
  api,
  generateDailyReport,
  generateImage,
  useApi,
  type DailyReportContent,
  type GeneratedImage,
} from '@/lib/api'
import { isFlagged, num, parseISODay, toISODate, todayISO } from '@/lib/metrics'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { useHeaderAction } from '@/lib/page-header'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { ActivityGraphSection } from '@/components/activity-graph-section'
import { GenerateButton } from '@/components/generate-button'
import { NextRun } from '@/components/next-run'
import { PeriodPicker } from '@/components/period-picker'
import { ReportEditor } from '@/components/report-editor'
import { ReportImageCard } from '@/components/report-image'

export function DailyReportPage({ initialDate }: { readonly initialDate?: string }) {
  const { t, locale } = useI18n()
  const reports = useApi('reports', api.reports)

  // `#/daily?date=2026-08-05` — the target of the report mail's button. Only
  // the initial value: once the page is open the picker owns the date, so a
  // stale link cannot fight the operator for control of it.
  const [date, setDate] = useState(initialDate || todayISO())
  const [content, setContent] = useState<DailyReportContent | null>(null)
  // The day the report was generated for, frozen at generate time. The editor
  // is keyed to this rather than to `date`: a draft deliberately survives a
  // picker switch (see the comment in report-editor.tsx), and labelling a
  // surviving Monday text with a Tuesday `period` would file it under the
  // wrong `report_versions` key on Save and diff it against the wrong history.
  const [contentPeriod, setContentPeriod] = useState<string | null>(null)
  // The illustrated card, once generated below. Held here rather than inside
  // the card component because the editor embeds it in the exported .docx and
  // saves it with the version.
  const [card, setCard] = useState<GeneratedImage | null>(null)
  const [imageBusy, setImageBusy] = useState(false)
  const [imageError, setImageError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fmt = useMemo(() => new Intl.NumberFormat(intlLocaleOf(locale)), [locale])

  // The chosen day as the reader's locale writes it — used by the empty state,
  // which has to name the day it is empty *for* to be worth more than "rien".
  const dayLabel = useMemo(() => {
    return new Intl.DateTimeFormat(intlLocaleOf(locale), {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    }).format(parseISODay(date))
  }, [date, locale])

  // The most recent day that actually has rows — the empty state's way out.
  // Carries its own formatted label: an ISO string in a button is a machine
  // talking, and the sentence right above it already says "5 août 2026".
  const lastDayWithData = useMemo(() => {
    let best: string | null = null
    for (const r of reports.data?.reports ?? []) {
      const d = toISODate(r.date)
      if (d && (best === null || d > best)) best = d
    }
    if (!best || best === date) return null
    const [y, m, d] = best.split('-').map(Number)
    return {
      iso: best,
      label: new Intl.DateTimeFormat(intlLocaleOf(locale), {
        day: 'numeric',
        month: 'long',
      }).format(new Date(y, m - 1, d)),
    }
  }, [reports.data, date, locale])

  const rows = useMemo(
    () => (reports.data?.reports ?? []).filter((r) => toISODate(r.date) === date),
    [reports.data, date],
  )

  // Same aggregates as the weekly page, for the one chosen day — arithmetic,
  // not prose, so the model call stays reserved for the report itself.
  const stats = useMemo(() => {
    const totals = rows.reduce(
      (a, r) => ({
        goulottes: a.goulottes + num(r.goulottes_m),
        cables: a.cables + num(r.cables_m),
        bureaux: a.bureaux + num(r.bureaux_termines),
        panneaux: a.panneaux + num(r.panneaux_raccordes),
      }),
      { goulottes: 0, cables: 0, bureaux: 0, panneaux: 0 },
    )
    const byTech = new Map<string, { count: number; goulottes: number; flagged: number }>()
    for (const r of rows) {
      const k = (r.technicien ?? '').trim() || '—'
      const p = byTech.get(k) ?? { count: 0, goulottes: 0, flagged: 0 }
      byTech.set(k, {
        count: p.count + 1,
        goulottes: p.goulottes + num(r.goulottes_m),
        flagged: p.flagged + (isFlagged(r.flag_review) ? 1 : 0),
      })
    }
    return {
      totals,
      byTech: [...byTech.entries()].sort((a, b) => b[1].count - a[1].count),
      flagged: rows.filter((r) => isFlagged(r.flag_review)).length,
      techniciens: new Set(rows.map((r) => (r.technicien ?? '').trim()).filter(Boolean)).size,
      chantiers: new Set(rows.map((r) => (r.chantier ?? '').trim()).filter(Boolean)).size,
    }
  }, [rows])

  const generate = async () => {
    setBusy(true)
    setError(null)
    setContent(null)
    setContentPeriod(null)
    try {
      setContent(await generateDailyReport(date, rows))
      setContentPeriod(date)
      // The card rides along with the report — one gesture, not two buttons
      // (the old second button was the 2026-08-10 change). It is fired after
      // the text so the editor is not blocked waiting on the image model, and
      // it fails alone: a card error never costs the report.
      void generateCard()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  // A separate busy/error pair from `generate`: the card finishes on its own
  // clock while the editor is already usable, and its failure is shown in its
  // own section rather than as a page-level error.
  const generateCard = async () => {
    setImageBusy(true)
    setImageError(null)
    setCard(null)
    try {
      const made = await generateImage(rows, t('image.dayTitle', { date }))
      setCard(made)
    } catch (err) {
      setImageError(err instanceof Error ? err.message : String(err))
    } finally {
      setImageBusy(false)
    }
  }

  // A different day means a different report: the previous day's card must not
  // sit under the new one waiting to be mistaken for it. The report text is
  // deliberately left alone — the draft survives the switch (report-editor's
  // documented intent) — but the snapshot means it keeps the day it was
  // generated for. A failed generate for the old day must not either.
  useEffect(() => {
    setCard(null)
    setImageError(null)
    setError(null)
  }, [date])

  // Generate sits beside the page title in the shared header, not on a second
  // line of its own — the title is already the widest thing on the page and the
  // one action belongs on it.
  useHeaderAction(<GenerateButton busy={busy} disabled={rows.length === 0} onClick={generate} />, [
    busy,
    rows.length,
    date,
    locale,
  ])

  if (reports.error) return <ErrorState message={reports.error} onRetry={reports.reload} />
  if (reports.loading) return <Skeleton className="mt-8 h-64 rounded-xl" />

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-6 pt-8"
    >
      <ActivityGraphSection rows={reports.data?.reports ?? []} date={date} onSelectDay={setDate} />

      {/* Which day, and when the machine sends this on its own — the two things
          the graph above cannot say for itself. */}
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <PeriodPicker mode="day" value={date} onChange={setDate} />
        <NextRun kind="daily" />
      </div>

      {error && <ErrorState message={error} onRetry={generate} />}

      {rows.length === 0 && !error && (
        <EmptyState
          icon={FileTextIcon}
          title={t('daily.emptyTitle', { date: dayLabel })}
          body={t('daily.emptyBody')}
          // Not a disabled "Générer" button: with no rows there is nothing to
          // generate *from*, and a greyed primary action in the middle of an
          // empty page is a dead end dressed up as a way out. The real way out
          // is the last day that has data, which the heatmap already knows.
          action={
            lastDayWithData && (
              <button
                type="button"
                onClick={() => setDate(lastDayWithData.iso)}
                className="border-line text-ink hover:bg-surface inline-flex items-center gap-2 rounded-md border px-3.5 py-2 text-sm transition-colors active:translate-y-px"
              >
                <ArrowUUpLeftIcon size={14} />
                {t('daily.goLastDay', { date: lastDayWithData.label })}
              </button>
            )
          }
        />
      )}

      {rows.length > 0 && (
        <>
          <div className="flex flex-wrap gap-x-12 gap-y-6">
            {[
              [fmt.format(rows.length), t('metric.total')],
              [fmt.format(stats.techniciens), t('metric.techniciens')],
              [fmt.format(stats.chantiers), t('weekly.chantiers')],
              [fmt.format(stats.flagged), t('metric.flagged')],
            ].map(([v, l]) => (
              <div key={l}>
                <p className="tabular text-ink text-3xl leading-none font-medium">{v}</p>
                <p className="text-ink-faint mt-1.5 text-xs">{l}</p>
              </div>
            ))}
          </div>

          <section className="flex flex-col gap-4">
            <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
              {t('panel.productionToday')}
            </h2>
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
              {[
                [fmt.format(stats.totals.goulottes), t('metric.goulottes'), 'm'],
                [fmt.format(stats.totals.cables), t('metric.cables'), 'm'],
                [fmt.format(stats.totals.bureaux), t('metric.bureaux'), ''],
                [fmt.format(stats.totals.panneaux), t('metric.panneaux'), ''],
              ].map(([v, l, u]) => (
                <div key={l}>
                  <p className="tabular text-ink text-2xl leading-none font-medium">
                    {v}
                    {u && <span className="text-ink-faint ms-1 text-xs">{u}</span>}
                  </p>
                  <p className="text-ink-faint mt-2 text-xs">{l}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
              {t('weekly.perTech')}
            </h2>
            <ul className="divide-line flex flex-col divide-y">
              {stats.byTech.map(([name, v]) => (
                <li key={name} className="flex items-baseline gap-4 py-2.5 first:pt-0 last:pb-0">
                  <span className="text-ink min-w-0 flex-1 truncate text-sm">{name}</span>
                  <span className="tabular text-ink-muted text-sm">{fmt.format(v.count)}</span>
                  <span className="tabular text-ink-faint w-20 text-end text-xs">
                    {fmt.format(v.goulottes)} m
                  </span>
                  <span className="tabular text-status-warn w-8 text-end text-xs">
                    {v.flagged || ''}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <ReportImageCard
            title={t('image.dayTitle', { date })}
            image={card}
            busy={imageBusy}
            error={imageError}
            onRetry={() => void generateCard()}
          />
        </>
      )}

      {content && (
        <ReportEditor
          kind="daily"
          period={contentPeriod ?? date}
          objet={content.objet}
          corps={content.corps}
          image={card?.data_uri ?? null}
          generatedBy={content.generated_by}
          figures={{
            rapports: rows.length,
            techniciens: stats.techniciens,
            chantiers: stats.chantiers,
            flagged: stats.flagged,
            goulottes: stats.totals.goulottes,
            cables: stats.totals.cables,
            bureaux: stats.totals.bureaux,
            panneaux: stats.totals.panneaux,
          }}
          byTech={stats.byTech.map(([name, v]) => ({ name, ...v }))}
        />
      )}
    </motion.div>
  )
}
