import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { CaretLeftIcon, CaretRightIcon, CopyIcon } from '@phosphor-icons/react'
import { api, useApi } from '@/lib/api'
import { isFlagged, num, toISODate } from '@/lib/metrics'
import { useI18n } from '@/lib/i18n'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'

const DAY_MS = 86_400_000

function iso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Monday of the week containing `d`. ISO weeks start Monday. */
function weekStart(d: Date) {
  const copy = new Date(d)
  copy.setHours(0, 0, 0, 0)
  const dow = (copy.getDay() + 6) % 7
  return new Date(copy.getTime() - dow * DAY_MS)
}

export function WeeklyReportPage() {
  const { t, locale } = useI18n()
  const reports = useApi('reports', api.reports)
  const [offset, setOffset] = useState(0)
  const [copied, setCopied] = useState(false)

  const fmt = useMemo(
    () => new Intl.NumberFormat(locale === 'ar' ? 'ar-MA' : locale === 'en' ? 'en-GB' : 'fr-FR'),
    [locale],
  )
  const dayName = useMemo(
    () => new Intl.DateTimeFormat(locale === 'ar' ? 'ar-MA' : locale === 'en' ? 'en-GB' : 'fr-FR', { weekday: 'short' }),
    [locale],
  )

  const start = useMemo(() => new Date(weekStart(new Date()).getTime() + offset * 7 * DAY_MS), [offset])
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => new Date(start.getTime() + i * DAY_MS)), [start])

  const week = useMemo(() => {
    const rows = (reports.data?.reports ?? []).filter((r) => {
      const d = toISODate(r.date)
      return d !== null && d >= iso(days[0]) && d <= iso(days[6])
    })

    const perDay = days.map((d) => rows.filter((r) => toISODate(r.date) === iso(d)))
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
      rows,
      perDay,
      totals,
      byTech: [...byTech.entries()].sort((a, b) => b[1].count - a[1].count),
      flagged: rows.filter((r) => isFlagged(r.flag_review)).length,
      techniciens: new Set(rows.map((r) => (r.technicien ?? '').trim()).filter(Boolean)).size,
      chantiers: new Set(rows.map((r) => (r.chantier ?? '').trim()).filter(Boolean)).size,
    }
  }, [reports.data, days])

  const copy = async () => {
    const lines = [
      `${t('weekly.title')} ${iso(days[0])} → ${iso(days[6])}`,
      '',
      `${t('metric.total')}: ${week.rows.length}`,
      `${t('metric.techniciens')}: ${week.techniciens}`,
      `${t('weekly.chantiers')}: ${week.chantiers}`,
      `${t('metric.flagged')}: ${week.flagged}`,
      '',
      `${t('metric.goulottes')}: ${week.totals.goulottes} m`,
      `${t('metric.cables')}: ${week.totals.cables} m`,
      `${t('metric.bureaux')}: ${week.totals.bureaux}`,
      `${t('metric.panneaux')}: ${week.totals.panneaux}`,
      '',
      ...week.byTech.map(([name, v]) => `- ${name}: ${v.count} (${v.goulottes} m)`),
    ]
    await navigator.clipboard.writeText(lines.join('\n'))
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }

  if (reports.error) return <ErrorState message={reports.error} onRetry={reports.reload} />
  if (reports.loading) return <Skeleton className="mt-8 h-64 rounded-xl" />

  const maxDay = Math.max(...week.perDay.map((d) => d.length), 1)

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-8 pt-8"
    >
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => setOffset((o) => o - 1)}
          aria-label={t('weekly.previous')}
          className="border-line text-ink-muted hover:text-ink rounded-md border p-1.5 transition-colors active:translate-y-px"
        >
          <CaretLeftIcon size={14} className="rtl:rotate-180" />
        </button>
        <span className="tabular text-ink text-sm">
          {iso(days[0])} → {iso(days[6])}
        </span>
        <button
          type="button"
          onClick={() => setOffset((o) => Math.min(0, o + 1))}
          disabled={offset >= 0}
          aria-label={t('weekly.next')}
          className="border-line text-ink-muted hover:text-ink rounded-md border p-1.5 transition-colors active:translate-y-px disabled:opacity-40"
        >
          <CaretRightIcon size={14} className="rtl:rotate-180" />
        </button>

        <button
          type="button"
          onClick={copy}
          className="border-line text-ink-muted hover:text-ink ms-auto flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors active:translate-y-px"
        >
          <CopyIcon size={13} />
          {copied ? t('daily.copied') : t('daily.copy')}
        </button>
      </div>

      {/* Computed locally from the Sheet: no model call, so the numbers are arithmetic, not prose. */}
      <p className="text-ink-faint max-w-[65ch] text-sm">{t('weekly.intro')}</p>

      {week.rows.length === 0 ? (
        <EmptyState body={t('weekly.noRows')} />
      ) : (
        <>
          <div className="flex flex-wrap gap-x-12 gap-y-6">
            {[
              [fmt.format(week.rows.length), t('metric.total')],
              [fmt.format(week.techniciens), t('metric.techniciens')],
              [fmt.format(week.chantiers), t('weekly.chantiers')],
              [fmt.format(week.flagged), t('metric.flagged')],
            ].map(([v, l]) => (
              <div key={l}>
                <p className="tabular text-ink text-3xl leading-none font-medium">{v}</p>
                <p className="text-ink-faint mt-1.5 text-xs">{l}</p>
              </div>
            ))}
          </div>

          <section className="flex flex-col gap-4">
            <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
              {t('weekly.perDay')}
            </h2>
            <div className="grid grid-cols-7 gap-2">
              {week.perDay.map((rows, i) => (
                <div key={i} className="flex flex-col items-center gap-2">
                  <div className="flex h-24 w-full items-end">
                    <motion.div
                      className="bg-accent w-full rounded-t-[4px]"
                      initial={{ height: 0 }}
                      animate={{ height: `${(rows.length / maxDay) * 100}%` }}
                      transition={{ type: 'spring', stiffness: 100, damping: 20, delay: i * 0.04 }}
                    />
                  </div>
                  <span className="tabular text-ink text-xs">{rows.length}</span>
                  <span className="text-ink-faint text-[0.6875rem] capitalize">{dayName.format(days[i])}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
              {t('panel.productionToday')}
            </h2>
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
              {[
                [fmt.format(week.totals.goulottes), t('metric.goulottes'), 'm'],
                [fmt.format(week.totals.cables), t('metric.cables'), 'm'],
                [fmt.format(week.totals.bureaux), t('metric.bureaux'), ''],
                [fmt.format(week.totals.panneaux), t('metric.panneaux'), ''],
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
              {week.byTech.map(([name, v]) => (
                <li key={name} className="flex items-baseline gap-4 py-2.5 first:pt-0 last:pb-0">
                  <span className="text-ink min-w-0 flex-1 truncate text-sm">{name}</span>
                  <span className="tabular text-ink-muted text-sm">{fmt.format(v.count)}</span>
                  <span className="tabular text-ink-faint w-20 text-end text-xs">{fmt.format(v.goulottes)} m</span>
                  <span className="tabular text-status-warn w-8 text-end text-xs">{v.flagged || ''}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </motion.div>
  )
}
