import { useMemo, useRef, useState } from 'react'
import { motion } from 'motion/react'
import {
  CalendarBlankIcon,
  CheckIcon,
  FlagIcon,
  MagnifyingGlassIcon,
  PencilSimpleIcon,
  XIcon,
} from '@phosphor-icons/react'
import {
  api,
  patchReport,
  useApi,
  type GeneratedReport,
  type ReportRow,
} from '@/lib/api'
import { isFlagged, num, toISODate, todayISO, clock } from '@/lib/metrics'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { ActivityGraphSection } from '@/components/activity-graph-section'
import { cn } from '@/lib/utils'

/**
 * The chantier (site name) is inserted by an admin or site manager, never
 * invented by the model: a technician who forgets to name the site leaves a
 * blank cell, and the operator fills it here. One click on the cell turns it
 * into an input; Enter saves through PATCH /reports/{row}, Esc cancels.
 */
function ChantierCell({ r, onSaved }: { readonly r: ReportRow; readonly onSaved: () => void }) {
  const { t } = useI18n()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  // Enter "saves" and unmounts the input, which fires a blur save on the same
  // frame — without a lock, one commit becomes two PATCHes.
  const saving = useRef(false)

  const start = () => {
    setValue(r.chantier ?? '')
    setError(null)
    setEditing(true)
  }
  const save = async () => {
    if (saving.current) return
    const next = value.trim()
    setEditing(false)
    if (next === (r.chantier ?? '')) return
    saving.current = true
    try {
      await patchReport(r._row, 'chantier', next)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      saving.current = false
    }
  }

  if (editing) {
    return (
      <span className="flex min-w-44 flex-col items-start gap-1">
        <span className="flex w-full items-center gap-1">
          <input
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void save()
              if (e.key === 'Escape') setEditing(false)
            }}
            onBlur={() => void save()}
            placeholder={t('reports.chantierPlaceholder')}
            aria-label={t('reports.chantierPlaceholder')}
            className="text-ink border-line focus:border-accent w-full min-w-0 rounded border bg-transparent px-1.5 py-0.5 text-sm outline-none"
          />
          <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => void save()} aria-label={t('common.save')}>
            <CheckIcon size={14} className="text-status-ok shrink-0" />
          </button>
          <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => setEditing(false)} aria-label={t('common.cancel')}>
            <XIcon size={14} className="text-ink-faint shrink-0" />
          </button>
        </span>
        {error && <span className="text-status-fail text-[0.6875rem]">{error}</span>}
      </span>
    )
  }

  return (
    <button
      type="button"
      onClick={start}
      title={t('reports.editChantier')}
      className="group text-ink-muted hover:text-ink inline-flex items-center gap-1.5 rounded px-1 py-0.5 text-start text-sm transition-colors"
    >
      {r.chantier || '—'}
      <PencilSimpleIcon
        size={12}
        className="text-ink-faint shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
      />
    </button>
  )
}

function LedgerRow({
  r,
  fmt,
  threshold,
  pad,
  onChantierSaved,
}: {
  readonly r: ReportRow
  readonly fmt: Intl.NumberFormat
  readonly threshold: number
  readonly pad: string
  readonly onChantierSaved: () => void
}) {
  const flagged = isFlagged(r.flag_review)
  const confidence = num(r.confidence)
  const { t } = useI18n()
  const { settings } = useSettings()

  return (
    <tr className="border-line hover:bg-surface border-b transition-colors last:border-b-0">
      <td className={cn('tabular text-ink-faint pe-4 align-top text-xs whitespace-nowrap', pad)}>
        {r.date}
        <span className="ms-2 opacity-70">
          {clock(r.heure, settings.timeFormat, t('time.am'), t('time.pm'))}
        </span>
      </td>
      <td className={cn('text-ink pe-4 align-top text-sm whitespace-nowrap', pad)}>
        {r.technicien || '—'}
      </td>
      <td className={cn('pe-4 align-top', pad)}>
        <ChantierCell r={r} onSaved={onChantierSaved} />
      </td>
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

/**
 * The "messages" tab: search / flag / day filters over the raw Sheet rows.
 *
 * Lifted out of ReportsPage with its own filter state — the page was one
 * function holding two unrelated tabs, and the filters are meaningless to the
 * generated tab anyway.
 */
function MessagesTab({
  reports,
  pad,
}: {
  readonly reports: ReturnType<typeof useApi<{ reports: ReportRow[] }>>
  readonly pad: string
}) {
  const { t, locale } = useI18n()
  const { settings } = useSettings()
  const [query, setQuery] = useState('')
  const [onlyFlagged, setOnlyFlagged] = useState(false)
  const [date, setDate] = useState('')
  const fmt = useMemo(() => new Intl.NumberFormat(intlLocaleOf(locale)), [locale])

  const rows = useMemo(() => {
    if (!reports.data) return []
    const q = query.trim().toLowerCase()
    // Newest first: the Sheet appends, so the tail is the most recent row.
    return [...reports.data.reports]
      .reverse()
      .filter((r) => (onlyFlagged ? isFlagged(r.flag_review) : true))
      .filter((r) => (date ? toISODate(r.date) === date : true))
      .filter((r) =>
        q
          ? [r.technicien, r.chantier, r.client, r.resume, r.observations]
              .filter(Boolean)
              .some((v) => String(v).toLowerCase().includes(q))
          : true,
      )
  }, [reports.data, query, onlyFlagged, date])

  return (
    <>
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
            onlyFlagged ? 'bg-slate-100 text-ink dark:bg-slate-850' : 'text-ink-muted hover:text-ink',
          )}
        >
          <FlagIcon size={13} weight={onlyFlagged ? 'fill' : 'regular'} />
          {t('metric.flagged')}
        </button>

        {date && (
          <button
            type="button"
            onClick={() => setDate('')}
            className="text-ink-faint hover:text-ink text-xs underline underline-offset-4"
          >
            {t('inbox.all')}
          </button>
        )}

        <span className="tabular text-ink-faint text-xs">{fmt.format(rows.length)}</span>
      </div>

      <ActivityGraphSection
        rows={reports.data?.reports ?? []}
        date={date || todayISO()}
        onSelectDay={(iso) => setDate(iso)}
      />

      {rows.length === 0 ? (
        <EmptyState body={query || onlyFlagged || date ? t('reports.noMatch') : undefined} />
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
                <LedgerRow
                  key={r._row}
                  r={r}
                  fmt={fmt}
                  threshold={settings.confidence}
                  pad={pad}
                  onChantierSaved={reports.reload}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

export function ReportsPage() {
  const { t, locale } = useI18n()
  const { settings } = useSettings()
  const reports = useApi('reports', api.reports, settings.refreshMs || undefined)
  const generated = useApi('reports/generated', api.generatedReports, settings.refreshMs || undefined)

  const [tab, setTab] = useState<'generated' | 'messages'>('generated')

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

  if (tab === 'generated' && generated.error) {
    return <ErrorState message={generated.error} onRetry={generated.reload} />
  }
  if (tab === 'messages' && reports.error) {
    return <ErrorState message={reports.error} onRetry={reports.reload} />
  }

  const loading = tab === 'generated' ? generated.loading : reports.loading
  if (loading) {
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
      <div className="flex flex-wrap items-center gap-4">
        <p className="text-ink-faint max-w-[60ch] text-sm">
          {tab === 'generated' ? t('reports.generatedIntro') : t('reports.messagesIntro')}
        </p>
        <fieldset className="border-line m-0 ms-auto flex rounded-md border p-0.5">
          <legend className="sr-only">{t('reports.tab.label')}</legend>
          {(['generated', 'messages'] as const).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setTab(k)}
              aria-pressed={tab === k}
              className={cn(
                'rounded px-2.5 py-1 text-xs transition-colors',
                tab === k
                  ? 'bg-slate-100 text-ink dark:bg-slate-850'
                  : 'text-ink-faint hover:text-ink',
              )}
            >
              {t(`reports.tab.${k}`)}
            </button>
          ))}
        </fieldset>
      </div>

      {tab === 'generated' ? (
        <div className="flex flex-col gap-3">
          {(generated.data?.reports ?? []).length === 0 ? (
            <EmptyState body={t('reports.noGenerated')} />
          ) : (
            (generated.data?.reports ?? []).map((g) => (
              <GeneratedCard key={`${g.manager_id}-${g.period}`} g={g} fmt={dt} />
            ))
          )}
        </div>
      ) : (
        <MessagesTab reports={reports} pad={pad} />
      )}
    </motion.div>
  )
}
