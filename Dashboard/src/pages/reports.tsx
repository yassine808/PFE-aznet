import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { CalendarBlankIcon } from '@phosphor-icons/react'
import { api, useApi, type GeneratedReport } from '@/lib/api'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

/** One stored generated report: manager, period badge, and the corps on demand. */
function GeneratedCard({
  g,
  fmt,
}: {
  readonly g: GeneratedReport
  readonly fmt: Intl.DateTimeFormat
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const daily = g.period_type !== 'weekly'

  return (
    <div className="border-line rounded-md border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-start"
      >
        <CalendarBlankIcon
          size={16}
          className={cn('shrink-0', daily ? 'text-accent' : 'text-status-warn')}
        />
        <span className="text-ink min-w-0 flex-1 truncate text-sm">
          {g.objet || `${g.manager_name} — ${g.period}`}
        </span>
        <span
          className={cn(
            'shrink-0 rounded-full px-2 py-0.5 text-[0.6875rem] font-medium',
            daily
              ? 'bg-accent/10 text-accent dark:bg-accent/20'
              : 'bg-status-warn/10 text-status-warn dark:bg-status-warn/20',
          )}
        >
          {daily ? t('reports.badge.daily') : t('reports.badge.weekly')}
        </span>
        <span className="tabular text-ink-faint hidden shrink-0 text-xs sm:block">
          {fmt.format(new Date(g.generated_at))}
        </span>
        <span className="text-ink-faint hidden shrink-0 text-xs md:block">
          {t('reports.generatedBy', { name: g.generated_by })}
        </span>
      </button>
      {open && (
        <div className="border-line border-t px-4 py-3">
          <p className="text-ink-faint mb-1 text-xs">
            {g.manager_name} · {g.period}
          </p>
          <p className="text-ink text-sm whitespace-pre-wrap">{g.corps}</p>
        </div>
      )}
    </div>
  )
}

export function ReportsPage() {
  const { t, locale } = useI18n()
  const { settings } = useSettings()
  const generated = useApi('reports/generated', api.generatedReports, settings.refreshMs || undefined)

  const dt = useMemo(
    () =>
      new Intl.DateTimeFormat(intlLocaleOf(locale), {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      }),
    [locale],
  )

  if (generated.error) return <ErrorState message={generated.error} onRetry={generated.reload} />

  if (generated.loading) {
    return (
      <div className="flex flex-col gap-3 pt-8">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-10" />
        ))}
      </div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-6 pt-8"
    >
      <p className="text-ink-faint max-w-[60ch] text-sm">{t('reports.generatedIntro')}</p>

      <div className="flex flex-col gap-3">
        {(generated.data?.reports ?? []).length === 0 ? (
          <EmptyState body={t('reports.noGenerated')} />
        ) : (
          (generated.data?.reports ?? []).map((g) => (
            <GeneratedCard key={`${g.manager_id}-${g.period}`} g={g} fmt={dt} />
          ))
        )}
      </div>
    </motion.div>
  )
}
