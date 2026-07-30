import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { FlagIcon, MagnifyingGlassIcon } from '@phosphor-icons/react'
import { api, useApi, type ReportRow } from '@/lib/api'
import { isFlagged, num } from '@/lib/metrics'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

function LedgerRow({
  r,
  fmt,
  threshold,
  pad,
}: {
  r: ReportRow
  fmt: Intl.NumberFormat
  threshold: number
  pad: string
}) {
  const flagged = isFlagged(r.flag_review)
  const confidence = num(r.confidence)

  return (
    <tr className="border-line hover:bg-surface border-b transition-colors last:border-b-0">
      <td className={cn('tabular text-ink-faint pe-4 align-top text-xs whitespace-nowrap', pad)}>
        {r.date}
        <span className="ms-2 opacity-70">{r.heure}</span>
      </td>
      <td className={cn('text-ink pe-4 align-top text-sm whitespace-nowrap', pad)}>
        {r.technicien || '—'}
      </td>
      <td className={cn('text-ink-muted pe-4 align-top text-sm', pad)}>{r.chantier || '—'}</td>
      <td className={cn('tabular text-ink pe-4 text-end align-top text-sm whitespace-nowrap', pad)}>
        {num(r.goulottes_m) ? fmt.format(num(r.goulottes_m)) : '·'}
      </td>
      <td className={cn('tabular text-ink pe-4 text-end align-top text-sm whitespace-nowrap', pad)}>
        {num(r.cables_m) ? fmt.format(num(r.cables_m)) : '·'}
      </td>
      <td className={cn('pe-4 align-top', pad)}>
        {/* Confidence as a bar, not a percentage: the eye compares lengths faster than digits. */}
        <span className="bg-line inline-block h-1 w-14 overflow-hidden rounded-full align-middle">
          <span
            className={cn(
              'block h-full rounded-full',
              confidence < threshold ? 'bg-status-warn' : 'bg-status-ok',
            )}
            style={{ width: `${Math.round(Math.min(Math.max(confidence, 0), 1) * 100)}%` }}
          />
        </span>
      </td>
      <td className={cn('align-top', pad)}>
        {flagged && <FlagIcon size={14} weight="fill" className="text-status-warn" />}
      </td>
    </tr>
  )
}

export function ReportsPage() {
  const { t, locale } = useI18n()
  const { settings } = useSettings()
  const reports = useApi('reports', api.reports, settings.refreshMs || undefined)

  const [query, setQuery] = useState('')
  const [onlyFlagged, setOnlyFlagged] = useState(false)

  const fmt = useMemo(
    () => new Intl.NumberFormat(locale === 'ar' ? 'ar-MA' : locale === 'en' ? 'en-GB' : 'fr-FR'),
    [locale],
  )

  const rows = useMemo(() => {
    if (!reports.data) return []
    const q = query.trim().toLowerCase()
    // Newest first: the Sheet appends, so the tail is the most recent row.
    return [...reports.data.reports]
      .reverse()
      .filter((r) => (onlyFlagged ? isFlagged(r.flag_review) : true))
      .filter((r) =>
        q
          ? [r.technicien, r.chantier, r.client, r.resume, r.observations]
              .filter(Boolean)
              .some((v) => String(v).toLowerCase().includes(q))
          : true,
      )
  }, [reports.data, query, onlyFlagged])

  if (reports.error) return <ErrorState message={reports.error} onRetry={reports.reload} />

  if (reports.loading) {
    return (
      <div className="flex flex-col gap-3 pt-8">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-10" />
        ))}
      </div>
    )
  }

  const pad = settings.density === 'compact' ? 'py-1.5' : 'py-3'

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-6 pt-8"
    >
      {/* Filters in one row above the table. */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="border-line focus-within:border-accent flex min-w-56 flex-1 items-center gap-2 rounded-md border px-3 py-2 transition-colors">
          <MagnifyingGlassIcon size={14} className="text-ink-faint shrink-0" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('reports.search')}
            aria-label={t('reports.search')}
            className="text-ink placeholder:text-ink-faint min-w-0 flex-1 bg-transparent text-sm outline-none"
          />
        </div>

        <button
          type="button"
          onClick={() => setOnlyFlagged((v) => !v)}
          aria-pressed={onlyFlagged}
          className={cn(
            'border-line flex items-center gap-2 rounded-md border px-3 py-2 text-xs transition-colors active:translate-y-px',
            onlyFlagged
              ? 'bg-slate-100 text-ink dark:bg-slate-850'
              : 'text-ink-muted hover:text-ink',
          )}
        >
          <FlagIcon size={13} weight={onlyFlagged ? 'fill' : 'regular'} />
          {t('metric.flagged')}
        </button>

        <span className="tabular text-ink-faint text-xs">{fmt.format(rows.length)}</span>
      </div>

      {rows.length === 0 ? (
        <EmptyState body={query || onlyFlagged ? t('reports.noMatch') : undefined} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[46rem] border-collapse text-start">
            <thead>
              <tr className="border-line text-ink-faint border-b text-start text-[0.6875rem] tracking-wide uppercase">
                <th className="py-2 pe-4 text-start font-medium">{t('col.when')}</th>
                <th className="py-2 pe-4 text-start font-medium">{t('col.technicien')}</th>
                <th className="py-2 pe-4 text-start font-medium">{t('col.chantier')}</th>
                <th className="py-2 pe-4 text-end font-medium">{t('metric.goulottes')}</th>
                <th className="py-2 pe-4 text-end font-medium">{t('metric.cables')}</th>
                <th className="py-2 pe-4 text-start font-medium">{t('col.confidence')}</th>
                <th className="py-2 text-start font-medium">
                  <span className="sr-only">{t('metric.flagged')}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <LedgerRow key={r._row} r={r} fmt={fmt} threshold={settings.confidence} pad={pad} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </motion.div>
  )
}
