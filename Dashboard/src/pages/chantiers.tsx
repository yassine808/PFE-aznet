import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  ArrowCounterClockwiseIcon,
  BellSlashIcon,
  BuildingsIcon,
  CheckCircleIcon,
  CheckIcon,
  MagnifyingGlassIcon,
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
  muteAlert,
  renameArticle,
  unmuteAlert,
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

/**
 * Sites, as a master–detail rather than a scroll.
 *
 * The page used to be four stacked full-width bands — unverified sites, the
 * article review queue, the alert list, then every site as an accordion — each
 * with a paragraph of its own. Opening two sites pushed the third off the
 * screen, and the two bands that ask for a decision sat above the list the
 * reader actually came for. Nothing was wrong with any one band; the stack was
 * the problem.
 *
 * Now: one list on the left, one pane on the right, and the two queues reached
 * from a chip instead of occupying the top of the page. The pane shows exactly
 * one thing at a time, so the page is about one screen tall whatever it holds.
 * Nothing was removed — the queues, the alerts and the confirm/delete actions
 * are all still here, one click away instead of one scroll.
 */

/** What the right-hand pane is showing. Exactly one thing, always. */
type View =
  | { readonly kind: 'site'; readonly id: number }
  | { readonly kind: 'alerts' }
  | { readonly kind: 'articles' }

const fade = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 140, damping: 22 } },
  exit: { opacity: 0, y: -4, transition: { duration: 0.12 } },
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
  const suffix = unit ? ` ${unit}` : ''
  return `${Number.isInteger(n) ? n : n.toFixed(1)}${suffix}`
}

/** Accent- and case-insensitive, because a spoken site name is neither. */
const norm = (s: string) =>
  s
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .trim()
    .toLowerCase()

/** Pane heading. A rule and a label — never a card. */
function Head({ title, aside }: { readonly title: string; readonly aside?: string }) {
  return (
    <div className="border-line flex items-baseline justify-between gap-3 border-b pb-1.5">
      <h2 className="text-ink-faint text-[0.6875rem] font-medium tracking-wide uppercase">
        {title}
      </h2>
      {aside && <span className="tabular text-ink-faint text-[0.6875rem]">{aside}</span>}
    </div>
  )
}

/**
 * A count that opens the pane on what it counts.
 *
 * Only a non-zero count is a chip. A zero shown as a dimmed pill is a button
 * that leads to an empty page, and a row of them is a row of dead ends.
 */
function Chip({
  label,
  n,
  tone,
  active,
  onClick,
}: {
  readonly label: string
  readonly n: number
  readonly tone: 'warn' | 'fail'
  readonly active: boolean
  readonly onClick: () => void
}) {
  if (n === 0) return null
  const hue =
    tone === 'fail'
      ? 'text-status-fail border-status-fail/40'
      : 'text-status-warn border-status-warn/40'
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`focus-visible:ring-accent flex shrink-0 cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-1 text-[0.6875rem] transition-colors outline-none focus-visible:ring-2 active:translate-y-px ${hue} ${
        active ? 'bg-surface-raised' : 'hover:bg-surface-raised/60'
      }`}
    >
      <span className="tabular font-medium">{n}</span>
      {label}
    </button>
  )
}

const btn =
  'border-line bg-surface text-ink hover:border-line-strong focus-visible:ring-accent inline-flex cursor-pointer items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors outline-none focus-visible:ring-2 active:translate-y-px disabled:opacity-50'
const btnDanger =
  'border-status-fail/40 text-status-fail hover:bg-status-fail focus-visible:ring-accent inline-flex cursor-pointer items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors outline-none hover:text-white focus-visible:ring-2 active:translate-y-px disabled:opacity-50'

/**
 * What is running out — permanently on screen, above everything else.
 *
 * This used to be a chip you had to click. A material shortage is the one
 * thing on this page with a deadline attached, and a count you have to open is
 * a count you can walk past; the band states the finding itself, so nobody has
 * to go looking for it.
 *
 * Bounded so it cannot become the scroll it replaced: three lines, then a
 * button that opens the rest in the pane. Dismissed findings are hidden here
 * and reachable one click away — never deleted, because a line you cannot see
 * is a line you cannot bring back.
 */
function AlertsBand({
  alerts,
  onOpenAll,
  showingAll,
}: {
  readonly alerts: ReturnType<typeof useApi<{ alerts: MaterialAlert[] }>>
  readonly onOpenAll: () => void
  readonly showingAll: boolean
}) {
  const { t } = useI18n()
  const [showIgnored, setShowIgnored] = useState(false)

  if (alerts.loading && !alerts.data) return <Skeleton className="h-12" />

  const rows = alerts.data?.alerts ?? []
  const live = rows.filter((a) => !a.ignored)
  const muted = rows.filter((a) => a.ignored)

  // Nothing to say, said in one line. An empty panel that occupies the same
  // space as a full one trains the reader to skip the space.
  if (live.length === 0 && muted.length === 0) {
    return (
      <p className="text-ink-faint flex items-center gap-2 text-[0.6875rem]">
        <CheckCircleIcon size={12} className="text-status-ok shrink-0" />
        {t('chantiers.alertsNone')}
      </p>
    )
  }

  const visible = showIgnored ? muted : live.slice(0, 3)
  const hidden = showIgnored ? 0 : live.length - visible.length

  return (
    <section className="border-line/70 flex flex-col gap-1 border-y py-1.5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-ink-faint flex items-center gap-1.5 text-[0.6875rem] font-medium tracking-wide uppercase">
          <TriangleIcon
            size={10}
            weight="fill"
            className={live.length > 0 ? 'text-status-fail' : 'text-ink-faint'}
          />
          {showIgnored ? t('chantiers.ignored') : t('chantiers.alerts')}
          <span className="tabular">{showIgnored ? muted.length : live.length}</span>
        </h2>
        <span className="flex items-center gap-3 text-[0.6875rem]">
          {muted.length > 0 && (
            <button
              type="button"
              onClick={() => setShowIgnored(!showIgnored)}
              className="text-ink-faint hover:text-ink cursor-pointer transition-colors"
            >
              {showIgnored
                ? t('chantiers.backToLive')
                : t('chantiers.ignoredCount', { n: String(muted.length) })}
            </button>
          )}
          {(hidden > 0 || showingAll) && !showIgnored && (
            <button
              type="button"
              onClick={onOpenAll}
              className="text-ink-muted hover:text-ink cursor-pointer transition-colors"
            >
              {showingAll ? t('chantiers.close') : t('chantiers.andMore', { n: String(hidden) })}
            </button>
          )}
        </span>
      </div>
      {live.length === 0 && !showIgnored ? (
        <p className="text-ink-faint text-[0.6875rem]">{t('chantiers.allIgnored')}</p>
      ) : (
        <ul className="divide-line/40 divide-y">
          {visible.map((a) => (
            <BandRow key={`${a.chantier}-${a.champ}`} alert={a} onDone={alerts.reload} />
          ))}
        </ul>
      )}
    </section>
  )
}

/** One line of the band: the finding, and the one button that silences it. */
function BandRow({
  alert: a,
  onDone,
  site = true,
}: {
  readonly alert: MaterialAlert
  readonly onDone: () => void
  /** False on a pane that is already one site, where naming it again is noise. */
  readonly site?: boolean
}) {
  const { t } = useI18n()
  const { user } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const tone = a.niveau === 'bas' ? 'text-status-warn' : 'text-status-fail'

  const run = (fn: () => Promise<unknown>) => async () => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      onDone()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5">
      {/* Never hue alone: the glyph, the written level and the figure all say it. */}
      <TriangleIcon size={9} weight="fill" className={`${tone} shrink-0`} />
      <span className="text-ink min-w-0 flex-1 truncate text-xs">
        <span className="font-medium">{a.article}</span>
        <span className="text-ink-faint">{site ? ` · ${a.chantier}` : ''}</span>
      </span>
      <span className={`${tone} shrink-0 text-[0.6875rem] font-medium`}>
        {t(`chantiers.level.${a.niveau}`)}
      </span>
      <span className={`tabular shrink-0 text-[0.6875rem] ${tone}`}>
        {a.niveau === 'depassement'
          ? t('chantiers.over', { n: num(Math.abs(a.reste ?? 0), a.unite) })
          : t('chantiers.remaining', { n: num(a.reste, a.unite) })}
      </span>
      {a.jours != null && (
        <span className="tabular text-ink-muted shrink-0 text-[0.6875rem] whitespace-nowrap">
          {t('chantiers.cover', { n: a.jours.toFixed(1) })}
        </span>
      )}
      {error && <span className="text-status-fail shrink-0 text-[0.625rem]">{error}</span>}
      {/* Any signed-in human may dismiss: `persons` only carries an account for
          a directeur or a chef, and the API gates the write on `require_human`
          anyway — a second rule here could only ever be the wrong one.

          Worded, bordered and 28px tall rather than a bare 12px glyph. A muted
          icon on a dense row reads as decoration, and this is the one control
          on the page that changes what everybody else sees — it has to look
          like a button and say what it does. The minimum touch target is the
          floor, not the target: 44px on a row this dense would push the
          figures onto a second line, so it takes the row's full height and
          keeps the hit area intact via the surrounding padding. */}
      {user && (
        <button
          type="button"
          disabled={busy}
          title={a.ignored ? t('chantiers.restoreHint') : t('chantiers.ignoreHint')}
          onClick={run(() =>
            a.ignored ? unmuteAlert(a.chantier, a.champ) : muteAlert(a.chantier, a.champ),
          )}
          className="border-line text-ink-muted hover:border-line-strong hover:text-ink focus-visible:ring-accent inline-flex h-7 shrink-0 cursor-pointer items-center gap-1.5 rounded-md border px-2.5 text-[0.6875rem] font-medium transition-colors outline-none focus-visible:ring-2 active:translate-y-px disabled:opacity-40"
        >
          {a.ignored ? (
            <ArrowCounterClockwiseIcon size={13} weight="bold" />
          ) : (
            <BellSlashIcon size={13} weight="bold" />
          )}
          {a.ignored ? t('chantiers.restore') : t('chantiers.ignore')}
        </button>
      )}
    </li>
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
 *
 * It is the *only* place a name is changed. `SiteMaterials` below shows the
 * same articles per site and offers no actions, because a second place to
 * rewrite a column header is a second way for two spellings to diverge.
 */
function ReviewArticles({
  articles,
}: {
  readonly articles: ReturnType<typeof useApi<{ articles: FreeArticle[] }>>
}) {
  const { t } = useI18n()
  const { user } = useAuth()
  const [busy, setBusy] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [pendingDelete, setPendingDelete] = useState<FreeArticle | null>(null)
  const [error, setError] = useState<string | null>(null)

  const pending = (articles.data?.articles ?? []).filter((a) => !a.confirmed)

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
    <div className="flex min-w-0 flex-col gap-3">
      <Head title={t('chantiers.materials')} aside={String(pending.length)} />
      <p className="text-ink-muted max-w-[70ch] text-[0.6875rem] leading-relaxed">
        {t('chantiers.materialsIntro')}
      </p>
      {pending.length === 0 ? (
        <EmptyState body={t('chantiers.materialsNone')} />
      ) : (
        <ul className="border-line divide-line/60 divide-y border-t">
          {pending.map((a) => (
            <li key={a.slug} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-2">
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
                    className={btn}
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
                        className={btn}
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
                        className={btn}
                      >
                        <PencilSimpleIcon size={11} />
                        {t('chantiers.rename')}
                      </button>
                      <button
                        type="button"
                        disabled={busy === a.slug}
                        onClick={() => setPendingDelete(a)}
                        className={btnDanger}
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
      )}
      {error && <p className="text-status-fail text-xs">{error}</p>}
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
    </div>
  )
}

/**
 * What this site declared that its bordereau never listed.
 *
 * The review queue only ever shows *unconfirmed* names, so an article
 * disappeared from the page the moment a director accepted or corrected it —
 * the one action that proves it is real. This is the opposite cut: every free
 * article that reached this site, confirmed or not, with the quantity summed
 * across its reports.
 */
function SiteMaterials({
  chantier,
  articles,
}: {
  readonly chantier: Chantier
  readonly articles: readonly FreeArticle[]
}) {
  const { t } = useI18n()

  // Matched on the site NAME, because that is what a report row snapshots —
  // the chantier is frozen onto the row so a later reassignment never rewrites
  // history, which means the id is not in the payload to match on.
  const key = norm(chantier.nom)
  const rows = articles
    .map((a) => ({ a, site: a.sites?.find((s) => norm(s.chantier) === key) }))
    .filter((r): r is { a: FreeArticle; site: NonNullable<FreeArticle['sites']>[number] } =>
      Boolean(r.site),
    )
    .sort((x, y) => y.site.qte - x.site.qte)

  if (rows.length === 0) return null

  return (
    <section className="flex min-w-0 flex-col gap-1">
      <h3 className="text-ink-faint text-[0.625rem] font-medium tracking-wide uppercase">
        {t('chantiers.declared')}
      </h3>
      {/* Two columns where there is room: this list is short lines and long
          gutters, and one column of it wastes half the pane's width. */}
      <ul className="border-line/60 grid border-t sm:grid-cols-2 sm:gap-x-8">
        {rows.map(({ a, site }) => (
          <li
            key={a.slug}
            className="border-line/40 flex items-baseline justify-between gap-3 border-b py-1.5"
          >
            <span className="text-ink flex min-w-0 items-baseline gap-2 text-xs">
              <span className="truncate">{a.designation}</span>
              {/* Colour never carries it alone — the word is there too. */}
              {!a.confirmed && (
                <span className="text-status-warn shrink-0 text-[0.625rem]">
                  {t('chantiers.toCheck')}
                </span>
              )}
            </span>
            <span className="tabular text-ink-muted shrink-0 text-xs whitespace-nowrap">
              {num(site.qte, a.unite ?? undefined)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** One contract line as a ledger row: figures right, meter under the percentage. */
function ArticleRow({ article: a }: { readonly article: BordereauArticle }) {
  const { t } = useI18n()
  const raw = a.avancement == null ? null : Number(a.avancement)
  const pct = raw == null || Number.isNaN(raw) ? null : Math.round(raw * 100)
  const over = pct != null && pct > 100

  return (
    <tr className="border-line/50 border-b last:border-0">
      <td className="text-ink-faint tabular hidden w-7 py-1.5 pe-2 align-top text-[0.625rem] sm:table-cell">
        {a.numero ?? '—'}
      </td>
      <td className="py-1.5 pe-3 align-top">
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
      <td className="tabular text-ink-muted py-1.5 pe-3 text-end align-top text-xs whitespace-nowrap">
        {num(a.qte_marche, a.unite)}
      </td>
      <td className="tabular text-ink py-1.5 pe-3 text-end align-top text-xs whitespace-nowrap">
        {num(a.qte_installee)}
      </td>
      <td className="w-24 py-1.5 align-top">
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
    <section className="flex min-w-0 flex-col gap-4">
      {[...lots.entries()].map(([lot, rows]) => (
        <div key={lot || '_'} className="flex min-w-0 flex-col gap-1">
          {named && (
            <h3 className="text-ink-faint text-[0.625rem] font-medium tracking-wide uppercase">
              {lot || t('chantiers.noTache')}
            </h3>
          )}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[28rem] text-xs">
              <thead>
                <tr className="text-ink-faint border-line border-b text-[0.625rem] uppercase">
                  <th className="hidden w-7 py-1 text-start font-medium sm:table-cell">
                    {t('chantiers.lineNo')}
                  </th>
                  <th className="py-1 text-start font-medium">{t('chantiers.article')}</th>
                  <th className="py-1 pe-3 text-end font-medium">{t('chantiers.marche')}</th>
                  <th className="py-1 pe-3 text-end font-medium">{t('chantiers.installed')}</th>
                  <th className="w-24 py-1 text-end font-medium">{t('chantiers.progress')}</th>
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
    </section>
  )
}

/**
 * One site, whole: what it is running out of, what it owes, what it declared,
 * and — while nobody has confirmed it exists — the two buttons that settle it.
 *
 * The confirm/delete pair used to live in a framed band at the top of the
 * page, above sites that needed no decision at all. It belongs on the site it
 * decides, where the reader can see the bordereau they are about to keep or
 * drop.
 */
function SiteDetail({
  chantier: c,
  articles,
  alerts,
  onAlertsChanged,
  onSettled,
}: {
  readonly chantier: Chantier
  readonly articles: readonly FreeArticle[]
  readonly alerts: readonly MaterialAlert[]
  readonly onAlertsChanged: () => void
  readonly onSettled: () => void
}) {
  const { t } = useI18n()
  const { user } = useAuth()
  const [busy, setBusy] = useState(false)
  // Deleting drops the bordereau with the site, so it goes through the same
  // dialog every destructive action in this dashboard goes through.
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const unverified = c.verifie === false
  const key = norm(c.nom)
  // Dismissed findings included: this pane is the whole truth about one site,
  // and the band above is the one that only shouts about what is still live.
  const mine = alerts.filter((a) => norm(a.chantier) === key)
  const meta = [c.client, c.sheet_tab && c.sheet_tab !== c.nom ? c.sheet_tab : null]
    .filter(Boolean)
    .join(' · ')

  const act = (fn: (id: number) => Promise<void>) => async () => {
    setBusy(true)
    setError(null)
    try {
      await fn(c.id)
      onSettled()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
      setConfirmDelete(false)
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <div className="border-line flex flex-wrap items-end justify-between gap-x-4 gap-y-2 border-b pb-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="text-ink flex min-w-0 items-center gap-2 text-base font-medium">
            <span className="truncate">{c.nom}</span>
            {unverified && (
              <WarningIcon size={12} weight="fill" className="text-status-warn shrink-0" />
            )}
          </h2>
          <p className="text-ink-faint truncate text-[0.6875rem]">
            {meta || (unverified ? t('chantiers.unverified') : t('chantiers.verified'))}
          </p>
        </div>
        {unverified && user?.role === 'directeur' && (
          <span className="flex shrink-0 items-center gap-2">
            <button type="button" disabled={busy} onClick={act(verifyChantier)} className={btn}>
              <CheckIcon size={11} />
              {t('chantiers.confirm')}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setConfirmDelete(true)}
              className={btnDanger}
            >
              {t('chantiers.delete')}
            </button>
          </span>
        )}
      </div>

      {unverified && (
        <p className="text-ink-muted max-w-[70ch] text-[0.6875rem] leading-relaxed">
          {t('chantiers.unverifiedIntro')}
        </p>
      )}
      {error && <p className="text-status-fail text-xs">{error}</p>}

      {mine.length > 0 && (
        <section className="flex min-w-0 flex-col gap-1">
          <h3 className="text-ink-faint text-[0.625rem] font-medium tracking-wide uppercase">
            {t('chantiers.alerts')}
          </h3>
          <ul className="border-line/60 divide-line/40 divide-y border-t">
            {mine.map((a) => (
              <BandRow
                key={`${a.chantier}-${a.champ}`}
                alert={a}
                site={false}
                onDone={onAlertsChanged}
              />
            ))}
          </ul>
        </section>
      )}

      <Bordereau chantier={c} />
      <SiteMaterials chantier={c} articles={articles} />

      <ConfirmDialog
        open={confirmDelete}
        target={c.nom}
        body={t('chantiers.deleteSure')}
        busy={busy}
        onConfirm={() => void act(deleteChantier)()}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  )
}

export function ChantiersPage() {
  const { t } = useI18n()
  const chantiers = useApi('chantiers', api.chantiers)
  // Fetched once here rather than inside the detail pane: `useApi` dedupes by
  // key anyway, but holding it at the page keeps a selected site from showing
  // a skeleton for data the page already has.
  const articles = useApi('free-articles', freeArticles)
  // 60s: an assessment costs a Sheets read per site and the server caches for
  // 120s anyway, so polling faster only spends the browser's battery.
  const alerts = useApi('alerts', api.alerts, 60_000)

  const [view, setView] = useState<View | null>(null)
  const [query, setQuery] = useState('')

  const sites = useMemo(() => chantiers.data?.chantiers ?? [], [chantiers.data])
  const registry = articles.data?.articles ?? []
  const rows = alerts.data?.alerts ?? []
  const pendingArticles = registry.filter((a) => !a.confirmed).length
  const pendingSites = sites.filter((c) => c.verifie === false).length

  const shown = useMemo(() => {
    const q = norm(query)
    if (!q) return sites
    return sites.filter((c) => norm(c.nom).includes(q) || norm(c.client ?? '').includes(q))
  }, [sites, query])

  // The first site is selected for you. A master–detail that opens on an empty
  // pane costs the reader a click to reach the state the page exists for.
  const selected =
    view?.kind === 'site'
      ? (sites.find((c) => c.id === view.id) ?? null)
      : view == null
        ? (shown[0] ?? null)
        : null

  // Worst first. An operator reads the top of a list, so ordering is the
  // cheapest way to make the line that means "order today" the line they see.
  const order = { depassement: 0, critique: 1, bas: 2 } as const
  const sortedAlerts = [...rows].sort((a, b) => order[a.niveau] - order[b.niveau])

  const paneKey =
    view?.kind === 'alerts'
      ? 'alerts'
      : view?.kind === 'articles'
        ? 'articles'
        : String(selected?.id ?? 'none')

  return (
    <div className="flex flex-col gap-4 pb-8">
      {/* One line: what to look at, and everything that wants a decision. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <label className="border-line bg-surface focus-within:ring-accent flex min-w-0 flex-1 items-center gap-2 rounded-md border px-2.5 py-1.5 focus-within:ring-2 sm:max-w-xs">
          <MagnifyingGlassIcon size={13} className="text-ink-faint shrink-0" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('chantiers.filter')}
            aria-label={t('chantiers.filter')}
            className="text-ink placeholder:text-ink-faint min-w-0 flex-1 bg-transparent text-sm outline-none"
          />
        </label>
        <Chip
          label={t('chantiers.materials')}
          n={pendingArticles}
          tone="warn"
          active={view?.kind === 'articles'}
          onClick={() => setView(view?.kind === 'articles' ? null : { kind: 'articles' })}
        />
        {/* Jumps to the first site awaiting a decision rather than opening a
            list of its own: the decision is taken on the site, in the pane. */}
        <Chip
          label={t('chantiers.unverified')}
          n={pendingSites}
          tone="warn"
          active={selected?.verifie === false}
          onClick={() => {
            const first = sites.find((c) => c.verifie === false)
            if (first) setView({ kind: 'site', id: first.id })
          }}
        />
      </div>

      {/* Always on screen: a shortage is the one thing here with a deadline. */}
      <AlertsBand
        alerts={alerts}
        showingAll={view?.kind === 'alerts'}
        onOpenAll={() => setView(view?.kind === 'alerts' ? null : { kind: 'alerts' })}
      />

      <div className="grid min-w-0 gap-6 lg:grid-cols-[15rem_1fr] xl:grid-cols-[17rem_1fr]">
        {/* Sticky rather than a second scrollbar: the shell scrolls the
            document, and a nested overflow container would trap the wheel
            everywhere except its own strip. */}
        <div className="flex min-w-0 flex-col gap-2 lg:sticky lg:top-4 lg:max-h-[calc(100dvh-3rem)] lg:overflow-y-auto lg:pe-1">
          <Head title={t('chantiers.all')} aside={String(shown.length)} />
          {chantiers.loading && !chantiers.data && <Skeleton className="h-32" />}
          {chantiers.error && <ErrorState message={chantiers.error} onRetry={chantiers.reload} />}
          {!chantiers.loading && !chantiers.error && shown.length === 0 && (
            <EmptyState body={query ? t('chantiers.noMatch') : t('chantiers.allNone')} />
          )}
          <ul className="divide-line/50 divide-y">
            {shown.map((c) => {
              const active = selected?.id === c.id
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => setView({ kind: 'site', id: c.id })}
                    aria-current={active}
                    className={`focus-visible:ring-accent relative flex w-full cursor-pointer items-center gap-2.5 py-2 ps-2.5 text-start transition-colors outline-none focus-visible:ring-2 ${
                      active ? 'bg-surface-raised' : 'hover:bg-surface-raised/50'
                    }`}
                  >
                    {/* Only the selected row takes the accent — DESIGN.md's Ten
                        Percent Rule. `layoutId` slides the mark between rows
                        rather than blinking it out and in, so the eye follows
                        the selection instead of re-finding it. */}
                    {active && (
                      <motion.span
                        layoutId="site-marker"
                        className="bg-accent absolute inset-y-1 start-0 w-0.5 rounded-full"
                        transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                      />
                    )}
                    <BuildingsIcon
                      size={14}
                      className={`shrink-0 ${c.verifie === false ? 'text-status-warn' : 'text-ink-faint'}`}
                    />
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="text-ink truncate text-[0.8125rem] leading-tight">
                        {c.nom}
                      </span>
                      {c.client && (
                        <span className="text-ink-faint truncate text-[0.625rem]">{c.client}</span>
                      )}
                    </span>
                    {c.verifie === false && (
                      <WarningIcon size={11} weight="fill" className="text-status-warn shrink-0" />
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        </div>

        {/* One thing at a time. Keyed on what is shown, so switching sites
            replays the entrance instead of mutating a pane in place. */}
        <div className="min-w-0">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={paneKey} variants={fade} initial="hidden" animate="show" exit="exit">
              {view?.kind === 'alerts' ? (
                <div className="flex min-w-0 flex-col gap-3">
                  <Head title={t('chantiers.alerts')} aside={String(rows.length)} />
                  <p className="text-ink-muted max-w-[70ch] text-[0.6875rem] leading-relaxed">
                    {t('chantiers.alertsIntro')}
                  </p>
                  <ul className="border-line divide-line/40 divide-y border-t">
                    {sortedAlerts.map((a) => (
                      <BandRow
                        key={`${a.chantier}-${a.champ}`}
                        alert={a}
                        site
                        onDone={alerts.reload}
                      />
                    ))}
                  </ul>
                </div>
              ) : view?.kind === 'articles' ? (
                <ReviewArticles articles={articles} />
              ) : selected ? (
                <SiteDetail
                  chantier={selected}
                  articles={registry}
                  alerts={rows}
                  onAlertsChanged={alerts.reload}
                  onSettled={() => {
                    chantiers.reload()
                    setView(null)
                  }}
                />
              ) : (
                !chantiers.loading && <EmptyState body={t('chantiers.pickSite')} />
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
