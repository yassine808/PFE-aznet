import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import {
  ArchiveIcon,
  CalendarBlankIcon,
  CalendarDotsIcon,
  MagnifyingGlassIcon,
  SparkleIcon,
  UserIcon,
} from '@phosphor-icons/react'
import { api, useApi, type GeneratedReport } from '@/lib/api'
import { useI18n, intlLocaleOf } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { cn } from '@/lib/utils'

type Filter = 'all' | 'daily' | 'weekly'

/** Stable identity for a stored report — the table is keyed `(manager_id, period)`. */
function keyOf(g: GeneratedReport): string {
  return `${g.manager_id}-${g.period}`
}

/**
 * Reports as a list beside a reading pane, not as a stack of accordions.
 *
 * The accordion version put every report at the same weight and hid all of
 * them: nine identical closed rows, and opening one pushed the rest off the
 * screen, so comparing this Friday's report with last Friday's meant scrolling
 * with one of them already forgotten. A list plus a pane is the shape the Inbox
 * already uses for exactly this question — pick one of many, read it whole —
 * and reusing it means the two pages are learned once.
 *
 * Under `lg` the pane moves below the list rather than beside it: at that width
 * a two-column split leaves neither column able to hold a paragraph.
 */
export function ReportsPage() {
  const { t, locale } = useI18n()
  const { settings } = useSettings()
  const generated = useApi(
    'reports/generated',
    api.generatedReports,
    settings.refreshMs || undefined,
  )

  const [filter, setFilter] = useState<Filter>('all')
  const [query, setQuery] = useState('')
  const [openKey, setOpenKey] = useState<string | null>(null)

  const dt = useMemo(
    () =>
      new Intl.DateTimeFormat(intlLocaleOf(locale), {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        hour12: settings.timeFormat === '12h',
      }),
    [locale, settings.timeFormat],
  )

  const all = generated.data?.reports ?? []

  const counts = useMemo(
    () => ({
      all: all.length,
      daily: all.filter((g) => g.period_type !== 'weekly').length,
      weekly: all.filter((g) => g.period_type === 'weekly').length,
    }),
    [all],
  )

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return all.filter((g) => {
      const weekly = g.period_type === 'weekly'
      if (filter === 'daily' && weekly) return false
      if (filter === 'weekly' && !weekly) return false
      if (!q) return true
      return `${g.manager_name} ${g.period} ${g.objet}`.toLowerCase().includes(q)
    })
  }, [all, filter, query])

  // The pane always shows something as long as the list does: an explicit
  // selection when there is one, otherwise the newest report in view. A blank
  // pane next to a full list reads as a loading failure.
  const open = shown.find((g) => keyOf(g) === openKey) ?? shown[0] ?? null

  if (generated.error) return <ErrorState message={generated.error} onRetry={generated.reload} />

  if (generated.loading) {
    return (
      <div className="grid gap-4 pt-8 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <div className="flex flex-col gap-2">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-16 rounded-md" />
          ))}
        </div>
        <Skeleton className="h-96 rounded-xl" />
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
      {/* No heading here: `App.tsx` renders the page title for every route. */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-ink-faint max-w-[48ch] text-sm">{t('reports.intro')}</p>

        <div className="flex flex-wrap items-center gap-2">
          {/* Segmented, not a select: three options that are all worth seeing,
              and each carries its own count so the split is legible at rest. */}
          <fieldset className="border-line m-0 flex rounded-md border p-0.5">
            <legend className="sr-only">{t('reports.filter')}</legend>
            {(['all', 'daily', 'weekly'] as const).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                aria-pressed={f === filter}
                className={cn(
                  'flex items-center gap-1.5 rounded px-2.5 py-1 text-xs transition-colors',
                  f === filter
                    ? 'bg-slate-100 text-ink dark:bg-slate-850'
                    : 'text-ink-faint hover:text-ink',
                )}
              >
                {t(`reports.filter.${f}`)}
                <span className="tabular opacity-60">{counts[f]}</span>
              </button>
            ))}
          </fieldset>

          <div className="border-line focus-within:border-accent flex items-center gap-2 rounded-md border px-2.5 py-1.5 transition-colors">
            <MagnifyingGlassIcon size={14} className="text-ink-faint shrink-0" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('reports.search')}
              aria-label={t('reports.search')}
              className="text-ink placeholder:text-ink-faint w-40 bg-transparent text-xs outline-none"
            />
          </div>
        </div>
      </div>

      {all.length === 0 && (
        <EmptyState
          icon={ArchiveIcon}
          title={t('reports.emptyTitle')}
          body={t('reports.emptyBody')}
          action={
            <a
              href="#/daily"
              className="bg-accent inline-flex items-center gap-2 rounded-md px-3.5 py-2 text-sm text-white transition-transform active:translate-y-px"
            >
              <SparkleIcon size={14} weight="fill" />
              {t('reports.emptyCta')}
            </a>
          }
        />
      )}

      {all.length > 0 && shown.length === 0 && (
        <EmptyState
          icon={MagnifyingGlassIcon}
          title={t('reports.noMatchTitle')}
          body={t('reports.noMatchBody')}
        />
      )}

      {all.length > 0 && shown.length > 0 && (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <ul className="flex max-h-[36rem] flex-col gap-1 overflow-y-auto pe-1">
            {shown.map((g) => (
              <ReportRow
                key={keyOf(g)}
                g={g}
                fmt={dt}
                active={open !== null && keyOf(open) === keyOf(g)}
                onOpen={() => setOpenKey(keyOf(g))}
              />
            ))}
          </ul>

          {open && <ReportPane g={open} fmt={dt} />}
        </div>
      )}
    </motion.div>
  )
}

/**
 * The report's own three shapes, drawn as three shapes.
 *
 * The prompt writes `## Synthèse` headings and `- ` bullets, and rendering the
 * whole thing as one pre-wrapped block showed the operator the hashes and the
 * dashes — the report's structure was present but had to be decoded. This is
 * not a Markdown parser and must not become one: three line shapes, no
 * dependency, and anything it does not recognise falls through as a paragraph,
 * which is the same thing the old code did to every line.
 */
function ReportBody({ corps }: { readonly corps: string }) {
  const lines = corps.split('\n')
  return (
    <div className="flex max-w-[75ch] flex-col gap-1.5">
      {lines.map((raw, i) => {
        const line = raw.trimEnd()
        const key = `${i}-${line.slice(0, 24)}`
        if (!line.trim()) return <span key={key} className="h-2" />
        // `[ \t]` rather than `\s`: the lines are already split on newlines, and
        // a `\s` that can match one makes the engine backtrack for nothing.
        // The capture is `([^ \t].*)?` rather than `(.*)`: those two can both
        // match the same run of spaces, and that ambiguity is what lets the
        // engine backtrack super-linearly. The same strings match — the greedy
        // `[ \t]+` has already eaten every space before the group starts.
        const heading = /^#{1,6}[ \t]+([^ \t].*)?$/.exec(line)
        if (heading) {
          return (
            <h3
              key={key}
              className="text-ink-faint mt-3 text-[0.6875rem] font-medium tracking-wide uppercase first:mt-0"
            >
              {heading[1]}
            </h3>
          )
        }
        const bullet = /^[ \t]*[-*•][ \t]+([^ \t].*)?$/.exec(line)
        if (bullet) {
          return (
            <p key={key} className="text-ink flex gap-2.5 text-sm leading-relaxed">
              <span aria-hidden className="bg-ink-faint mt-2 size-1 shrink-0 rounded-full" />
              <span className="min-w-0">{bullet[1]}</span>
            </p>
          )
        }
        return (
          <p key={key} className="text-ink text-sm leading-relaxed">
            {line}
          </p>
        )
      })}
    </div>
  )
}

/** One line in the list: what it is, whose it is, when it was made. */
function ReportRow({
  g,
  fmt,
  active,
  onOpen,
}: {
  readonly g: GeneratedReport
  readonly fmt: Intl.DateTimeFormat
  readonly active: boolean
  readonly onOpen: () => void
}) {
  const { t } = useI18n()
  const weekly = g.period_type === 'weekly'
  const Icon = weekly ? CalendarDotsIcon : CalendarBlankIcon

  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        aria-current={active ? 'true' : undefined}
        className={cn(
          'flex w-full items-start gap-2.5 rounded-md px-3 py-2.5 text-start transition-colors',
          // The selected row is a tonal step, never the accent: the accent has
          // one job on this page and it is the empty state's call to action.
          active ? 'bg-slate-100 dark:bg-slate-850' : 'hover:bg-surface',
        )}
      >
        <Icon size={15} className={cn('mt-0.5 shrink-0', active ? 'text-ink' : 'text-ink-faint')} />
        <span className="min-w-0 flex-1">
          <span className="text-ink block truncate text-sm">
            {g.objet || `${g.manager_name} — ${g.period}`}
          </span>
          <span className="text-ink-faint mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[0.6875rem]">
            <span className="tabular">{g.period}</span>
            <span aria-hidden>·</span>
            <span className="truncate">{g.manager_name}</span>
          </span>
        </span>
        <span className="flex shrink-0 flex-col items-end gap-1">
          <span className="text-ink-faint text-[0.6875rem]">
            {weekly ? t('reports.badge.weekly') : t('reports.badge.daily')}
          </span>
          <span className="tabular text-ink-faint text-[0.6875rem]">
            {fmt.format(new Date(g.generated_at))}
          </span>
        </span>
      </button>
    </li>
  )
}

/** The report itself, read whole. */
function ReportPane({
  g,
  fmt,
}: {
  readonly g: GeneratedReport
  readonly fmt: Intl.DateTimeFormat
}) {
  const { t } = useI18n()
  const weekly = g.period_type === 'weekly'

  return (
    <motion.article
      // Keyed on the report, so switching rows re-runs the entrance: the pane
      // changing under a click should be felt, not just noticed.
      key={keyOf(g)}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="border-line bg-surface edge flex min-w-0 flex-col rounded-xl border"
    >
      <header className="border-line flex flex-col gap-3 border-b px-5 py-4">
        <h2 className="text-ink text-sm font-medium">
          {g.objet || `${g.manager_name} — ${g.period}`}
        </h2>
        <div className="text-ink-faint flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs">
          <span className="flex items-center gap-1.5">
            {weekly ? <CalendarDotsIcon size={13} /> : <CalendarBlankIcon size={13} />}
            <span className="tabular">{g.period}</span>
          </span>
          <span className="flex items-center gap-1.5">
            <UserIcon size={13} />
            {g.manager_name}
          </span>
          <span className="tabular">{fmt.format(new Date(g.generated_at))}</span>
          {/* "automatique" is the backend's marker for a scheduled run, not a
              person: printing it raw read "Généré par automatique". Same branch
              as the report editor, and the same wording as the .docx. */}
          <span className="ms-auto">
            {g.generated_by && g.generated_by !== 'automatique'
              ? t('daily.generatedBy', { name: g.generated_by })
              : t('daily.generatedAuto')}
          </span>
        </div>
      </header>

      <div className="max-h-[30rem] overflow-y-auto px-5 py-4">
        <ReportBody corps={g.corps} />
      </div>
    </motion.article>
  )
}
