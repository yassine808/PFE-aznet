import { useState } from 'react'
import { motion } from 'motion/react'
import { BuildingsIcon, TriangleIcon, WarningIcon } from '@phosphor-icons/react'
import {
  api,
  bordereau,
  deleteChantier,
  useApi,
  verifyChantier,
  type Chantier,
  type MaterialAlert,
} from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useI18n } from '@/lib/i18n'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'

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

const num = (v: number | null | undefined, unit?: string) =>
  v == null ? '—' : `${Number.isInteger(v) ? v : v.toFixed(1)}${unit ? ` ${unit}` : ''}`

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

  return (
    <Band title={t('chantiers.alerts')} aside={String(rows.length)}>
      <p className="text-ink-muted max-w-[70ch] text-xs leading-relaxed">
        {t('chantiers.alertsIntro')}
      </p>
      <ul className="flex flex-col gap-2">
        {rows.map((a) => (
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
  const tone =
    alert.niveau === 'bas'
      ? 'text-status-warn'
      : 'text-status-fail'

  return (
    <li className="border-line flex flex-col gap-1 rounded-md border px-3 py-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-ink flex min-w-0 items-center gap-2 text-sm">
          <TriangleIcon size={12} weight="fill" className={`${tone} shrink-0`} />
          <span className="truncate font-medium">{alert.article}</span>
          <span className="text-ink-faint truncate text-xs">{alert.chantier}</span>
        </span>
        <span className="tabular flex items-baseline gap-3 text-xs">
          <span className={tone}>
            {alert.niveau === 'depassement'
              ? t('chantiers.over', { n: num(Math.abs(alert.reste ?? 0), alert.unite) })
              : t('chantiers.remaining', { n: num(alert.reste, alert.unite) })}
          </span>
          {alert.jours != null && (
            <span className="text-ink-muted">
              {t('chantiers.cover', { n: alert.jours.toFixed(1) })}
            </span>
          )}
        </span>
      </div>
      {/* The provenance travels with the number, always. */}
      {alert.source && <p className="text-ink-faint text-[0.6875rem]">{alert.source}</p>}
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
 */
function UnverifiedSites({ chantiers }: { readonly chantiers: ReturnType<typeof useApi<{ chantiers: Chantier[] }>> }) {
  const { t } = useI18n()
  const { user } = useAuth()
  const [busy, setBusy] = useState<number | null>(null)
  // Deleting drops the bordereau with the site, so it takes a second click.
  const [armed, setArmed] = useState<number | null>(null)
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
      setArmed(null)
    }
  }

  return (
    <motion.div variants={rise}>
      <Band title={t('chantiers.unverified')} aside={String(pending.length)}>
        <p className="text-ink-muted max-w-[70ch] text-xs leading-relaxed">
          {t('chantiers.unverifiedIntro')}
        </p>
        <ul className="mt-1 flex flex-col gap-2">
          {pending.map((c) => (
            <li
              key={c.id}
              className="border-line flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2"
            >
              <span className="text-ink flex min-w-0 items-center gap-2 text-sm">
                <WarningIcon size={14} className="text-status-warn shrink-0" />
                <span className="truncate">{c.nom}</span>
              </span>
              {user?.role === 'directeur' && (
                <span className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={busy === c.id}
                    onClick={act(c.id, verifyChantier)}
                    className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent cursor-pointer rounded-md border px-2.5 py-1 text-xs transition-colors outline-none focus-visible:ring-2 disabled:opacity-50"
                  >
                    {t('chantiers.confirm')}
                  </button>
                  <button
                    type="button"
                    disabled={busy === c.id}
                    onClick={armed === c.id ? act(c.id, deleteChantier) : () => setArmed(c.id)}
                    className={`focus-visible:ring-accent cursor-pointer rounded-md px-2.5 py-1 text-xs transition-colors outline-none focus-visible:ring-2 disabled:opacity-50 ${
                      armed === c.id
                        ? 'bg-status-fail text-white'
                        : 'border-line text-ink-muted hover:text-ink border'
                    }`}
                  >
                    {armed === c.id ? t('chantiers.deleteSure') : t('chantiers.delete')}
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
        {error && <p className="text-status-fail text-xs">{error}</p>}
      </Band>
    </motion.div>
  )
}

/** The contract, against what the journal says was installed against it. */
function Bordereau({ chantier }: { readonly chantier: Chantier }) {
  const { t } = useI18n()
  const data = useApi(`bordereau-${chantier.id}`, (s) => bordereau(chantier.id, s))

  if (data.loading && !data.data) return <Skeleton className="h-24" />
  if (data.error) return <ErrorState message={data.error} onRetry={data.reload} />

  const articles = data.data?.articles ?? []
  if (articles.length === 0) return <EmptyState body={t('chantiers.noBordereau')} />

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[34rem] text-xs">
        <thead>
          <tr className="text-ink-faint border-line border-b text-[0.6875rem] uppercase">
            <th className="py-1.5 text-start font-medium">{t('chantiers.article')}</th>
            <th className="py-1.5 text-end font-medium">{t('chantiers.marche')}</th>
            <th className="py-1.5 text-end font-medium">{t('chantiers.installed')}</th>
            <th className="w-24 py-1.5 text-end font-medium">{t('chantiers.progress')}</th>
          </tr>
        </thead>
        <tbody>
          {articles.map((a) => {
            const pct = a.avancement == null ? null : Math.round(a.avancement * 100)
            return (
              <tr key={a.id} className="border-line/60 border-b last:border-0">
                <td className="text-ink py-1.5 pe-3">{a.designation}</td>
                <td className="tabular text-ink-muted py-1.5 text-end">
                  {num(a.qte_marche, a.unite)}
                </td>
                {/* null is "not tracked here" (a switch, an onduleur), never
                    "none installed" — so it prints a dash, not a zero. */}
                <td className="tabular text-ink py-1.5 text-end">{num(a.qte_installee)}</td>
                <td className="py-1.5 text-end">
                  {pct == null ? (
                    <span className="text-ink-faint">—</span>
                  ) : (
                    <span className="flex items-center justify-end gap-2">
                      <span className="bg-line h-1 w-12 overflow-hidden rounded-full">
                        <span
                          className={`block h-full rounded-full ${pct > 100 ? 'bg-status-fail' : 'bg-accent'}`}
                          style={{ width: `${Math.min(100, pct)}%` }}
                        />
                      </span>
                      <span
                        className={`tabular w-9 text-end ${pct > 100 ? 'text-status-fail' : 'text-ink-muted'}`}
                      >
                        {pct}%
                      </span>
                    </span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
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
      <motion.div variants={rise}>
        <MaterialAlerts />
      </motion.div>

      <UnverifiedSites chantiers={chantiers} />

      <motion.div variants={rise}>
        <Band title={t('chantiers.all')} aside={String(sites.length)}>
          {chantiers.loading && !chantiers.data && <Skeleton className="h-24" />}
          {chantiers.error && (
            <ErrorState message={chantiers.error} onRetry={chantiers.reload} />
          )}
          {!chantiers.loading && sites.length === 0 && (
            <EmptyState body={t('chantiers.none')} />
          )}
          <ul className="flex flex-col gap-2">
            {sites.map((c) => (
              <li key={c.id} className="border-line rounded-md border">
                <button
                  type="button"
                  onClick={() => setOpen(open === c.id ? null : c.id)}
                  aria-expanded={open === c.id}
                  className="focus-visible:ring-accent flex w-full cursor-pointer items-center justify-between gap-3 px-3 py-2 text-start outline-none focus-visible:ring-2"
                >
                  <span className="text-ink flex min-w-0 items-center gap-2 text-sm">
                    <BuildingsIcon size={14} className="text-ink-faint shrink-0" />
                    <span className="truncate">{c.nom}</span>
                    {c.verifie === false && (
                      <WarningIcon size={12} className="text-status-warn shrink-0" />
                    )}
                  </span>
                  <span className="text-ink-faint truncate text-xs">
                    {c.client || c.sheet_tab || ''}
                  </span>
                </button>
                {open === c.id && (
                  <div className="border-line border-t px-3 py-2">
                    <Bordereau chantier={c} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        </Band>
      </motion.div>
    </motion.div>
  )
}
