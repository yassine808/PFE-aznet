import { useMemo } from 'react'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { PRIMARY_QUANTITIES, type QuantityTotal, type TechStat } from '@/lib/report-stats'

/**
 * The two panels the Daily and Weekly pages share: the production tiles and
 * the per-technician list. Identical markup on both pages, so it lives once.
 */

/** A column nobody has translated is named by its own schema field, stripped
 *  of the unit suffix the tile already prints. Not UI copy — the vocabulary is
 *  the Sheet's, and inventing a French label for an article here would just be
 *  a second, drifting copy of `journal.NUMERIC_COLUMNS`.
 *  ponytail: replace with the backend catalogue's labels when an endpoint
 *  serves them. */
function humanize(column: string): string {
  const bare = column.replace(/_(m|min|u)$/, '').replaceAll('_', ' ')
  return bare.charAt(0).toUpperCase() + bare.slice(1)
}

export function ReportTotals({ totals }: { readonly totals: readonly QuantityTotal[] }) {
  const { t, locale } = useI18n()
  const fmt = useMemo(() => new Intl.NumberFormat(intlLocaleOf(locale)), [locale])

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
        {t('panel.productionToday')}
      </h2>
      <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
        {totals.map(({ column, unit, value }) => {
          const key = PRIMARY_QUANTITIES[column] ?? `metric.${column}`
          const label = t(key)
          return (
            <div key={column}>
              <p className="tabular text-ink text-2xl leading-none font-medium">
                {fmt.format(value)}
                {unit && <span className="text-ink-faint ms-1 text-xs">{unit}</span>}
              </p>
              <p className="text-ink-faint mt-2 text-xs">
                {label === key ? humanize(column) : label}
              </p>
            </div>
          )
        })}
      </div>
    </section>
  )
}

export function ReportPerTech({ byTech }: { readonly byTech: readonly [string, TechStat][] }) {
  const { t, locale } = useI18n()
  const fmt = useMemo(() => new Intl.NumberFormat(intlLocaleOf(locale)), [locale])

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-ink-faint border-line border-b pb-2 text-[0.6875rem] font-medium tracking-wide uppercase">
        {t('weekly.perTech')}
      </h2>
      <ul className="divide-line flex flex-col divide-y">
        {byTech.map(([name, v]) => (
          <li key={name} className="flex items-baseline gap-4 py-2.5 first:pt-0 last:pb-0">
            <span className="text-ink min-w-0 flex-1 truncate text-sm">{name}</span>
            <span className="tabular text-ink-muted text-sm">{fmt.format(v.count)}</span>
            <span className="tabular text-ink-faint w-20 text-end text-xs">
              {fmt.format(v.goulottes)} m
            </span>
            <span className="tabular text-status-warn w-8 text-end text-xs">{v.flagged || ''}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
