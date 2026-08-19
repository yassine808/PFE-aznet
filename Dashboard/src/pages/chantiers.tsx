import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  BuildingsIcon,
  CaretRightIcon,
  CheckIcon,
  PencilSimpleIcon,
  TriangleIcon,
  WarningIcon,
} from '@phosphor-icons/react'
import {
  api,
  bordereau,
  confirmArticle,
  deleteArticle,
  deleteChantier,
  freeArticles,
  renameArticle,
  useApi,
  verifyChantier,
  type BordereauArticle,
  type Chantier,
  type FreeArticle,
  type MaterialAlert,
} from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useI18n } from '@/lib/i18n'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { ConfirmDialog } from '@/components/confirm-dialog'

const rise = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 100, damping: 20 } },
}

/** Section heading. Same shape as Overview's: a rule and a label, no box. */
function Band({
  title,
  aside,
  children,
}: {
  readonly title: string
  readonly aside?: string
  readonly children: React.ReactNode
}) {
  return (
    <section className="flex min-w-0 flex-col gap-3">
      <div className="border-line flex items-baseline justify-between gap-3 border-b pb-1.5">
        <h2 className="text-ink-faint text-[0.6875rem] font-medium tracking-wide uppercase">
          {title}
        </h2>
        {aside && <span className="tabular text-ink-faint text-[0.6875rem]">{aside}</span>}
      </div>
      {children}
    </section>
  )
}

/**
 * A quantity, or a dash.
 *
 * The `Number()` is defensive on purpose. The API owes us a number and now
 * sends one (`logs._iso` unwraps Postgres NUMERIC), but it used to send the
 * string `"144"`: this function called `.toFixed()` on it, threw during
 * render, and with no error boundary above it the entire dashboard unmounted
 * to a blank page the moment a site was opened. A parse here costs nothing and
 * turns the next wrong type upstream into a dash rather than a white screen.
 */
const num = (v: number | null | undefined, unit?: string) => {
  const n = v == null ? null : Number(v)
  if (n == null || Number.isNaN(n)) return '—'
  return `${Number.isInteger(n) ? n : n.toFixed(1)}${unit ? ` ${unit}` : ''}`
}

/**
 * What is running out, over the contract, or about to be.
 *
 * Read-only on purpose: every figure is arithmetic done in `app/stock.py` over
 * the journal, the receptions ledger and the bordereau. Nothing here recomputes
 * a quantity — a second arithmetic in the browser is a second answer to the
 * same question, and the mail already carries the first.
 */
function MaterialAlerts() {
  const { t } = useI18n()
  // 60s: an assessment costs a Sheets read per site and the server caches for
  // 120s anyway, so polling faster only spends the browser's battery.
  const alerts = useApi('alerts', api.alerts, 60_000)

  if (alerts.loading && !alerts.data) return <Skeleton className="h-24" />
  if (alerts.error) return <ErrorState message={alerts.error} onRetry={alerts.reload} />

  const rows = alerts.data?.alerts ?? []
  if (rows.length === 0) {
    return (
      <Band title={t('chantiers.alerts')}>
        <EmptyState body={t('chantiers.alertsNone')} />
      </Band>
    )
  }

  // Worst first. An operator reads the top of a list, so ordering is the
  // cheapest way to make the line that means "order today" the line they see.
  const order = { depassement: 0, critique: 1, bas: 2 } as const
  const sorted = [...rows].sort((a, b) => order[a.niveau] - order[b.niveau])

  return (
    <Band title={t('chantiers.alerts')} aside={String(rows.length)}>
      <p className="text-ink-muted max-w-[70ch] text-xs leading-relaxed">
        {t('chantiers.alertsIntro')}
      </p>
      <ul className="border-line divide-line/70 divide-y border-t">
        {sorted.map((a) => (
          <AlertRow key={`${a.chantier}-${a.champ}`} alert={a} />
        ))}
      </ul>
    </Band>
  )
}

function AlertRow({ alert }: { readonly alert: MaterialAlert }) {
  const { t } = useI18n()
  // The Ten Percent Rule: only the level that means "order today" takes the
  // alarm colour. A page where everything is red is a page where nothing is.
  const tone = alert.niveau === 'bas' ? 'text-status-warn' : 'text-status-fail'

  return (
    <li className="grid gap-x-4 gap-y-1 py-2.5 sm:grid-cols-[1fr_auto]">
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-ink flex min-w-0 items-center gap-2 text-sm">
          {/* Never hue alone: the glyph and the written level both carry it. */}
          <TriangleIcon size={11} weight="fill" className={`${tone} shrink-0`} />
          <span className="truncate font-medium">{alert.article}</span>
          <span className={`${tone} shrink-0 text-[0.6875rem] font-medium`}>
            {t(`chantiers.level.${alert.niveau}`)}
          </span>
        </span>
        {/* The provenance travels with the number, always. */}
        <span className="text-ink-faint ps-[1.15rem] text-[0.6875rem] leading-relaxed">
          {alert.chantier}
          {alert.source ? ` · ${alert.source}` : ''}
        </span>
      </div>
      <div className="tabular flex items-baseline gap-4 ps-[1.15rem] text-xs sm:ps-0">
        <span className={tone}>
          {alert.niveau === 'depassement'
            ? t('chantiers.over', { n: num(Math.abs(alert.reste ?? 0), alert.unite) })
            : t('chantiers.remaining', { n: num(alert.reste, alert.unite) })}
        </span>
        {alert.jours != null && (
          <span className="text-ink-muted whitespace-nowrap">
            {t('chantiers.cover', { n: alert.jours.toFixed(1) })}
          </span>
        )}
      </div>
    </li>
  )
}

/**
 * Sites the pipeline invented from a spoken name nobody has confirmed.
 *
 * Moved here from Overview (2026-08-16): a site is a real entity — it owns a
 * journal tab, a bordereau and a crew — and confirming one is site
 * administration, not a headline. Overview answers "what is happening today";
 * this page is where sites are looked after.
 *
 * It is the one framed surface on the page, and it is framed because it is the
 * only thing here that asks for a decision — and because as a plain band it
 * was indistinguishable from the list of real sites two bands below it.
 */
function UnverifiedSites({
  chantiers,
}: {
  readonly chantiers: ReturnType<typeof useApi<{ chantiers: Chantier[] }>>
}) {
  const { t } = useI18n()
  const { user } = useAuth()
  const [busy, setBusy] = useState<number | null>(null)
  // Deleting drops the bordereau with the site, so it goes through the same
  // dialog every destructive action in this dashboard goes through.
  const [pendingDelete, setPendingDelete] = useState<Chantier | null>(null)
  const [error, setError] = useState<string | null>(null)

  const pending = (chantiers.data?.chantiers ?? []).filter((c) => c.verifie === false)
  if (pending.length === 0) return null

  const act = (id: number, fn: (id: number) => Promise<void>) => async () => {
    setBusy(id)
    setError(null)
    try {
      await fn(id)
      chantiers.reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
      setPendingDelete(null)
    }
  }

  return (
    <motion.div variants={rise}>
      <section className="border-status-warn/30 bg-status-warn/5 flex flex-col gap-3 rounded-lg border p-4 sm:p-5">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-ink flex items-center gap-2 text-sm font-medium">
            <WarningIcon size={14} weight="fill" className="text-status-warn shrink-0" />
            {t('chantiers.unverified')}
          </h2>
          <span className="tabular text-ink-faint text-[0.6875rem]">{pending.length}</span>
        </div>
        <p className="text-ink-muted max-w-[70ch] text-xs leading-relaxed">
          {t('chantiers.unverifiedIntro')}
        </p>
        <ul className="divide-line/70 border-line/70 divide-y border-t">
          {pending.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="text-ink min-w-0 truncate text-sm">{c.nom}</span>
              {user?.role === 'directeur' && (
                <span className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={busy === c.id}
                    onClick={act(c.id, verifyChantier)}
                    className="border-line bg-surface text-ink hover:border-line-strong focus-visible:ring-accent cursor-pointer rounded-md border px-2.5 py-1 text-xs transition-colors outline-none focus-visible:ring-2 active:translate-y-px disabled:opacity-50"
                  >
                    {t('chantiers.confirm')}
                  </button>
                  <button
                    type="button"
                    disabled={busy === c.id}
                    onClick={() => setPendingDelete(c)}
                    className="border-status-fail/40 text-status-fail hover:bg-status-fail focus-visible:ring-accent cursor-pointer rounded-md border px-2.5 py-1 text-xs transition-colors outline-none hover:text-white focus-visible:ring-2 active:translate-y-px disabled:opacity-50"
                  >
                    {t('chantiers.delete')}
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
        {error && <p className="text-status-fail text-xs">{error}</p>}
      </section>
      <ConfirmDialog
        open={pendingDelete !== null}
        target={pendingDelete?.nom ?? ''}
        body={t('chantiers.deleteSure')}
        busy={busy !== null}
        onConfirm={() => {
          if (pendingDelete) void act(pendingDelete.id, deleteChantier)()
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </motion.div>
  )
}

/**
 * Articles a technician reported that no bordereau lists.
 *
 * A review, not an approval gate. The column and its figures already exist by
 * the time a row appears here — the pipeline never makes a technician wait for
 * a human — so the three actions are about the *name*: accept it, correct it,
 * or reject a reading nobody recognises. Correcting onto an existing name
 * merges the two columns, which is the only way to join two spellings the
 * normaliser cannot: "prise 2P+T" and "prise industrielle 2P+T" are one socket
 * to an electrician and two different word sets to a machine.
 */
function FreeArticles() {
  const { t } = useI18n()
  const { user } = useAuth()
  const articles = useApi('free-articles', freeArticles)
  const [busy, setBusy] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [pendingDelete, setPendingDelete] = useState<FreeArticle | null>(null)
  const [error, setError] = useState<string | null>(null)

  const pending = (articles.data?.articles ?? []).filter((a) => !a.confirmed)
  if (articles.loading && !articles.data) return <Skeleton className="h-20" />
  if (pending.length === 0) return null

  const run = (slug: string, fn: () => Promise<void>) => async () => {
    setBusy(slug)
    setError(null)
    try {
      await fn()
      articles.reload()
      setEditing(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
      setPendingDelete(null)
    }
  }

  return (
    <motion.div variants={rise}>
      <Band title={t('chantiers.materials')} aside={String(pending.length)}>
        <p className="text-ink-muted max-w-[70ch] text-xs leading-relaxed">
          {t('chantiers.materialsIntro')}
        </p>
        <ul className="border-line divide-line/70 divide-y border-t">
          {pending.map((a) => (
            <li key={a.slug} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-2.5">
              {editing === a.slug ? (
                <>
                  <input
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder={t('chantiers.renamePlaceholder')}
                    aria-label={t('chantiers.rename')}
                    className="border-line bg-surface text-ink focus-visible:ring-accent min-w-0 flex-1 rounded-md border px-2 py-1 text-sm outline-none focus-visible:ring-2"
                  />
                  <button
                    type="button"
                    disabled={busy === a.slug || !draft.trim()}
                    onClick={run(a.slug, () => renameArticle(a.slug, draft.trim()))}
                    className="border-line bg-surface text-ink hover:border-line-strong cursor-pointer rounded-md border px-2.5 py-1 text-xs transition-colors active:translate-y-px disabled:opacity-50"
                  >
                    {t('chantiers.save')}
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditing(null)}
                    className="text-ink-faint hover:text-ink cursor-pointer text-xs transition-colors"
                  >
                    {t('chantiers.cancel')}
                  </button>
                </>
              ) : (
                <>
                  <span className="text-ink min-w-0 flex-1 truncate text-sm">{a.designation}</span>
                  <span className="tabular text-ink-faint shrink-0 text-[0.6875rem]">
                    {t('chantiers.seen', { n: String(a.seen) })}
                  </span>
                  {user?.role === 'directeur' && (
                    <span className="flex shrink-0 items-center gap-2">
                      <button
                        type="button"
                        disabled={busy === a.slug}
                        onClick={run(a.slug, () => confirmArticle(a.slug))}
                        className="border-line bg-surface text-ink hover:border-line-strong focus-visible:ring-accent inline-flex cursor-pointer items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors outline-none focus-visible:ring-2 active:translate-y-px disabled:opacity-50"
                      >
                        <CheckIcon size={11} />
                        {t('chantiers.confirm')}
                      </button>
                      <button
                        type="button"
                        disabled={busy === a.slug}
                        onClick={() => {
                          setEditing(a.slug)
                          setDraft(a.designation)
                        }}
                        className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent inline-flex cursor-pointer items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors outline-none focus-visible:ring-2 active:translate-y-px disabled:opacity-50"
                      >
                        <PencilSimpleIcon size={11} />
                        {t('chantiers.rename')}
                      </button>
                      <button
                        type="button"
                        disabled={busy === a.slug}
                        onClick={() => setPendingDelete(a)}
                        className="border-status-fail/40 text-status-fail hover:bg-status-fail focus-visible:ring-accent cursor-pointer rounded-md border px-2.5 py-1 text-xs transition-colors outline-none hover:text-white focus-visible:ring-2 active:translate-y-px disabled:opacity-50"
                      >
                        {t('chantiers.delete')}
                      </button>
                    </span>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
        {error && <p className="text-status-fail text-xs">{error}</p>}
      </Band>
      <ConfirmDialog
        open={pendingDelete !== null}
        target={pendingDelete?.designation ?? ''}
        body={t('chantiers.deleteArticleSure')}
        busy={busy !== null}
        onConfirm={() => {
          if (pendingDelete) void run(pendingDelete.slug, () => deleteArticle(pendingDelete.slug))()
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </motion.div>
  )
}

/** One contract line as a ledger row: figures right, meter under the percentage. */
function ArticleRow({ article: a }: { readonly article: BordereauArticle }) {
  const { t } = useI18n()
  const raw = a.avancement == null ? null : Number(a.avancement)
  const pct = raw == null || Number.isNaN(raw) ? null : Math.round(raw * 100)
  const over = pct != null && pct > 100

  return (
    <tr className="border-line/60 border-b last:border-0">
      <td className="text-ink-faint tabular hidden w-8 py-2 pe-2 align-top text-[0.6875rem] sm:table-cell">
        {a.numero ?? '—'}
      </td>
      <td className="py-2 pe-3 align-top">
        <span className="text-ink block text-xs leading-snug">{a.designation}</span>
        {/* Keyed on `champ`, not on a null quantity. The API returns null for
            both "this line has no daily counterpart" (a switch, an onduleur)
            and "this line is tracked but the journal has nothing against it
            yet", and only the first is *hors suivi* — labelling both that way
            would tell the director sixteen tracked cable lines are untracked.
            The quantity stays a dash either way: printing 0 would claim a
            measurement nobody took. */}
        {a.champ == null && (
          <span
            className="text-ink-faint mt-0.5 block text-[0.625rem]"
            title={t('chantiers.untrackedHint')}
          >
            {t('chantiers.untracked')}
          </span>
        )}
      </td>
      <td className="tabular text-ink-muted py-2 pe-3 text-end align-top text-xs whitespace-nowrap">
        {num(a.qte_marche, a.unite)}
      </td>
      <td className="tabular text-ink py-2 pe-3 text-end align-top text-xs whitespace-nowrap">
        {num(a.qte_installee)}
      </td>
      <td className="w-28 py-2 align-top">
        {pct == null ? (
          <span className="text-ink-faint block text-end text-xs">—</span>
        ) : (
          <span className="flex flex-col items-end gap-1">
            <span
              className={`tabular text-[0.6875rem] ${over ? 'text-status-fail' : 'text-ink-muted'}`}
            >
              {pct}%
            </span>
            {/* scaleX, not width: DESIGN.md forbids animating layout properties. */}
            <span className="bg-line block h-1 w-full overflow-hidden rounded-full">
              <motion.span
                className={`block h-full w-full rounded-full ${over ? 'bg-status-fail' : 'bg-accent'}`}
                initial={{ scaleX: 0 }}
                animate={{ scaleX: Math.min(100, pct) / 100 }}
                style={{ transformOrigin: 'left' }}
                transition={{ type: 'spring', stiffness: 100, damping: 20 }}
              />
            </span>
          </span>
        )}
      </td>
    </tr>
  )
}

/**
 * The contract, against what the journal says was installed against it.
 *
 * Grouped by `tache` — the lot a line belongs to. That column has been in the
 * payload since the bordereaux were seeded and the table that used to live
 * here threw it away, so a reader got nineteen undifferentiated lines where
 * the director's own file has two or three named lots.
 */
function Bordereau({ chantier }: { readonly chantier: Chantier }) {
  const { t } = useI18n()
  const data = useApi(`bordereau-${chantier.id}`, (s) => bordereau(chantier.id, s))

  if (data.loading && !data.data) return <Skeleton className="h-24" />
  if (data.error) return <ErrorState message={data.error} onRetry={data.reload} />

  const articles = data.data?.articles ?? []
  if (articles.length === 0) return <EmptyState body={t('chantiers.noBordereau')} />

  // Insertion-ordered on purpose, so lots keep the order the bordereau was
  // seeded in rather than an alphabetical one nobody on site would recognise.
  const lots = new Map<string, BordereauArticle[]>()
  for (const a of articles) {
    const key = a.tache?.trim() || ''
    const bucket = lots.get(key)
    if (bucket) bucket.push(a)
    else lots.set(key, [a])
  }
  // A single unnamed lot is not a grouping, it is the whole list — no heading.
  const named = lots.size > 1 || !lots.has('')

  return (
    <div className="flex flex-col gap-5">
      {[...lots.entries()].map(([lot, rows]) => (
        <div key={lot || '_'} className="flex flex-col gap-1.5">
          {named && (
            <h4 className="text-ink-faint text-[0.625rem] font-medium tracking-wide uppercase">
              {lot || t('chantiers.noTache')}
            </h4>
          )}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[30rem] text-xs">
              <thead>
                <tr className="text-ink-faint border-line border-b text-[0.625rem] uppercase">
                  <th className="hidden w-8 py-1.5 text-start font-medium sm:table-cell">
                    {t('chantiers.lineNo')}
                  </th>
                  <th className="py-1.5 text-start font-medium">{t('chantiers.article')}</th>
                  <th className="py-1.5 pe-3 text-end font-medium">{t('chantiers.marche')}</th>
                  <th className="py-1.5 pe-3 text-end font-medium">{t('chantiers.installed')}</th>
                  <th className="w-28 py-1.5 text-end font-medium">{t('chantiers.progress')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <ArticleRow key={a.id} article={a} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}

/** One site as a disclosure row: hairline rules, no card — DESIGN.md §4. */
function SiteRow({
  chantier: c,
  open,
  onToggle,
}: {
  readonly chantier: Chantier
  readonly open: boolean
  readonly onToggle: () => void
}) {
  const { t } = useI18n()
  const unverified = c.verifie === false

  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-label={open ? t('chantiers.close') : t('chantiers.open')}
        className="group hover:bg-surface-raised/60 focus-visible:ring-accent flex w-full cursor-pointer items-center gap-3 py-3 text-start transition-colors outline-none focus-visible:ring-2"
      >
        {/* Rotation rather than a swapped glyph: the caret is the same object
            before and after, so the row reads as opening, not as redrawing.
            Mirrored under RTL, where "forward" points the other way. */}
        <motion.span
          animate={{ rotate: open ? 90 : 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 26 }}
          className="text-ink-faint group-hover:text-ink-muted flex shrink-0 rtl:-scale-x-100"
        >
          <CaretRightIcon size={13} weight="bold" />
        </motion.span>
        <BuildingsIcon
          size={15}
          className={`shrink-0 ${unverified ? 'text-status-warn' : 'text-ink-faint'}`}
        />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-ink truncate text-sm font-medium">{c.nom}</span>
          {c.client && <span className="text-ink-faint truncate text-[0.6875rem]">{c.client}</span>}
        </span>
        {unverified ? (
          <span className="text-status-warn border-status-warn/40 flex shrink-0 items-center gap-1 rounded border px-1.5 py-px text-[0.625rem]">
            <WarningIcon size={9} weight="fill" />
            {t('chantiers.unverified')}
          </span>
        ) : (
          <span className="text-ink-faint hidden shrink-0 text-[0.625rem] sm:inline">
            {t('chantiers.verified')}
          </span>
        )}
        {/* The journal tab, and only when it differs from the site name —
            which it usually does not, and a column repeating the label two
            inches to its left is noise pretending to be data. */}
        {c.sheet_tab && c.sheet_tab !== c.nom && (
          <span className="text-ink-faint tabular hidden w-32 shrink-0 truncate text-end text-[0.6875rem] md:inline">
            {c.sheet_tab}
          </span>
        )}
      </button>
      {/* Fades and lifts rather than unrolling: height is a layout property and
          DESIGN.md rules out animating one. */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ type: 'spring', stiffness: 140, damping: 22 }}
            className="border-line/70 ms-[1.65rem] border-s ps-4 pb-4"
          >
            <Bordereau chantier={c} />
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  )
}

export function ChantiersPage() {
  const { t } = useI18n()
  const chantiers = useApi('chantiers', api.chantiers)
  const [open, setOpen] = useState<number | null>(null)

  const sites = chantiers.data?.chantiers ?? []

  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.05 } } }}
      className="flex flex-col gap-8 pb-12"
    >
      {/* First, and only when it exists: it is the only band that asks the
          director to do something, and it disappears once nothing is pending. */}
      <UnverifiedSites chantiers={chantiers} />

      <FreeArticles />

      <motion.div variants={rise}>
        <MaterialAlerts />
      </motion.div>

      <motion.div variants={rise}>
        <Band title={t('chantiers.all')} aside={String(sites.length)}>
          {chantiers.loading && !chantiers.data && <Skeleton className="h-24" />}
          {chantiers.error && <ErrorState message={chantiers.error} onRetry={chantiers.reload} />}
          {!chantiers.loading && !chantiers.error && sites.length === 0 && (
            <EmptyState body={t('chantiers.allNone')} />
          )}
          {sites.length > 0 && (
            <ul className="divide-line/70 border-line divide-y border-b">
              {sites.map((c) => (
                <SiteRow
                  key={c.id}
                  chantier={c}
                  open={open === c.id}
                  onToggle={() => setOpen(open === c.id ? null : c.id)}
                />
              ))}
            </ul>
          )}
        </Band>
      </motion.div>
    </motion.div>
  )
}
