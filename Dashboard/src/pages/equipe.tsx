import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import {
  ArrowsClockwiseIcon,
  KeyIcon,
  PlusIcon,
  TrashIcon,
  UserMinusIcon,
  XIcon,
} from '@phosphor-icons/react'
import {
  addPerson,
  addTechnician,
  api,
  deletePerson,
  deleteTechnician,
  deleteUser,
  refreshProfile,
  setManager,
  useApi,
  type ReportRow,
  type Technician,
} from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useI18n } from '@/lib/i18n'
import { isFlagged, num, toISODate } from '@/lib/metrics'
import { ChannelIcon } from '@/components/channel-icon'
import { EmptyState, ErrorState, Skeleton } from '@/components/states'
import { GrantAccessForm, HistBlock } from '@/components/team-activity'
import { cn } from '@/lib/utils'

/**
 * The org chart: who works for whom, and everything about one colleague.
 *
 * Replaces the old `team` (accounts) and `access` (bot authorisation) pages,
 * which were two views of one table's worth of humans since `users` folded into
 * `persons`. A chef who also sends voice notes used to appear on both, as two
 * unrelated rows; here they are one box with a crew under it.
 *
 * Three fixed bands, never recursive: `role` decides the band and `manager_id`
 * decides the column. That is the real aznet org, and it is what lets this be a
 * group-by instead of a recursive component with a cycle guard.
 */

const CHANNELS = ['telegram', 'whatsapp'] as const

/**
 * Technicians shown side by side before a crew wraps to the next row.
 *
 * Three, because four 10rem boxes plus their gaps already push a chart with two
 * chefs past a 1440px viewport — and the page body scrolling sideways is the
 * thing DESIGN.md rules out.
 */
const CREW_PER_ROW = 3

/**
 * Chefs: always one row.
 *
 * Wrapping them to a second line used to leave a lone chef stranded under
 * empty space rather than under the directeur's line, which read as broken
 * rather than as "ran out of room". The chart already scrolls horizontally
 * (`overflow-x-auto` + `min-w-max`) for a wide crew row, so the same trade is
 * made here: more chefs widen the chart instead of wrapping it.
 */
function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = []
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size))
  return out
}

/**
 * Everything one person's rows say about them.
 *
 * Computed once, in one place, because the chart card and the detail panel were
 * otherwise going to answer the same question with two different arithmetics —
 * and the first time the two disagreed, both would be suspect.
 */
export interface PersonStats {
  count: number
  flagged: number
  /** Most recent report, ISO — null when the Sheet carries no parsable date. */
  last: string | null
  /** Distinct chantiers touched. */
  sites: number
  goulottes: number
  cables: number
  bureaux: number
  panneaux: number
  /**
   * Share of the raw transcript written in Arabic script, or null when nothing
   * was transcribed. Script-based: arabizi (darija in latin letters) reads as
   * French here, which the label admits.
   */
  pctArabic: number | null
}

function statsOf(rows: ReportRow[]): PersonStats {
  let arabic = 0
  let latin = 0
  let last: string | null = null
  const sites = new Set<string>()
  const totals = { goulottes: 0, cables: 0, bureaux: 0, panneaux: 0 }

  for (const r of rows) {
    const iso = toISODate(r.date)
    if (iso && (last === null || iso > last)) last = iso
    const site = (r.chantier ?? '').trim()
    if (site) sites.add(site.toLowerCase())
    totals.goulottes += num(r.goulottes_m)
    totals.cables += num(r.cables_m)
    totals.bureaux += num(r.bureaux_termines)
    totals.panneaux += num(r.panneaux_raccordes)

    for (const ch of (r.rapport_complet ?? '').replace(/\s+/g, '')) {
      const code = ch.codePointAt(0) ?? 0
      if (code >= 0x0600 && code <= 0x06ff) arabic += 1
      else if (/[a-zA-ZàâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ]/.test(ch)) latin += 1
    }
  }

  const script = arabic + latin
  return {
    count: rows.length,
    flagged: rows.filter((r) => isFlagged(r.flag_review)).length,
    last,
    sites: sites.size,
    ...totals,
    pctArabic: script === 0 ? null : Math.round((arabic / script) * 100),
  }
}

/** Reports per person, keyed by lower-cased name (the Sheet's own join key). */
type Load = Map<string, PersonStats>

export function EquipePage() {
  const { t } = useI18n()
  const { user } = useAuth()
  const list = useApi('technicians', api.technicians)
  // Same cache key the Reports page uses, so this costs no extra request when
  // the operator has already been there — and one otherwise.
  const reports = useApi('reports', api.reports)

  const [selected, setSelected] = useState<number | null>(null)
  const [adding, setAdding] = useState<'chef' | 'tech' | null>(null)
  const [error, setError] = useState<string | null>(null)
  // personId -> the manager we have asked for but not yet seen confirmed.
  const [pending, setPending] = useState<Map<number, number | null>>(new Map())

  const isDirector = user?.role === 'directeur'
  const people = useMemo(() => {
    const rows = list.data?.technicians ?? []
    if (pending.size === 0) return rows
    return rows.map((p) => (pending.has(p.id) ? { ...p, manager_id: pending.get(p.id)! } : p))
  }, [list.data, pending])

  // Clear overrides the server has caught up with, so a stale entry cannot pin
  // someone in place after a later move.
  useEffect(() => {
    if (pending.size === 0) return
    const rows = list.data?.technicians ?? []
    const settled = rows.filter((p) => pending.has(p.id) && p.manager_id === pending.get(p.id))
    if (settled.length === 0) return
    setPending((m) => {
      const next = new Map(m)
      for (const p of settled) next.delete(p.id)
      return next
    })
  }, [list.data, pending])

  const directeur = people.find((p) => p.role === 'directeur')
  const chefs = people.filter((p) => p.role === 'chef')
  const techs = people.filter((p) => p.role !== 'directeur' && p.role !== 'chef')
  // Unassigned techs get their own column rather than being dropped: a colleague
  // nobody owns is exactly the thing this page exists to make visible.
  const orphans = techs.filter((p) => !p.manager_id || !chefs.some((c) => c.id === p.manager_id))

  const focus = people.find((p) => p.id === selected) ?? null

  /**
   * How much each person has actually sent, keyed by lower-cased name — the
   * same key `_manager_buckets` uses server-side, because the Sheet carries a
   * name and not a channel id.
   *
   * The chart used to answer only "who reports to whom", which is the one thing
   * about an org that rarely changes. Volume is what a manager is looking for
   * when they open it: who is carrying the week, and who has gone quiet.
   */
  const load = useMemo(() => {
    const byName = new Map<string, ReportRow[]>()
    for (const r of reports.data?.reports ?? []) {
      const key = (r.technicien ?? '').trim().toLowerCase()
      if (!key) continue
      const bucket = byName.get(key)
      if (bucket) bucket.push(r)
      else byName.set(key, [r])
    }
    const m: Load = new Map()
    for (const [key, rows] of byName) m.set(key, statsOf(rows))
    return m
  }, [reports.data])

  // Bars are comparable across the chart or they are decoration, so every one
  // is drawn against the busiest person rather than against its own row.
  const peak = useMemo(() => Math.max(1, ...[...load.values()].map((v) => v.count)), [load])

  // Escape closes the detail panel, matching the mobile nav drawer's affordance.
  useEffect(() => {
    if (!focus) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setSelected(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [focus])

  /**
   * Reassign, showing the move immediately.
   *
   * The box has to travel the moment it is dropped: waiting for the PATCH and
   * the reload means the chart sits still for a beat and then the person is
   * simply somewhere else, which reads as a glitch rather than as a move. The
   * override is dropped once the server's own list arrives, and on failure the
   * box springs back to where it was — which is the honest thing for the UI to
   * do when the write did not land.
   */
  const move = async (personId: number, managerId: number | null) => {
    setError(null)
    setPending((m) => new Map(m).set(personId, managerId))
    try {
      await setManager(personId, managerId)
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setPending((m) => {
        const next = new Map(m)
        next.delete(personId)
        return next
      })
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-8 pt-8"
    >
      <div className="flex flex-wrap items-center gap-4">
        <p className="text-ink-faint max-w-[60ch] text-sm">{t('equipe.intro')}</p>
        {isDirector && (
          <span className="ms-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => setAdding((v) => (v === 'chef' ? null : 'chef'))}
              aria-expanded={adding === 'chef'}
              className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2"
            >
              <PlusIcon size={13} weight="bold" />
              {t('equipe.addChef')}
            </button>
            <button
              type="button"
              onClick={() => setAdding((v) => (v === 'tech' ? null : 'tech'))}
              aria-expanded={adding === 'tech'}
              className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2"
            >
              <PlusIcon size={13} weight="bold" />
              {t('equipe.addTech')}
            </button>
          </span>
        )}
      </div>

      {/* The add form is a drawer, not a centred window: it opens from the same
          edge and with the same spring as the detail panel, so "look at one
          person" and "add a person" are one gesture in two directions rather
          than two unrelated surfaces — and neither one covers the chart. */}
      <AnimatePresence>
        {adding && isDirector && (
          <Drawer
            label={t(adding === 'chef' ? 'equipe.addChef' : 'equipe.addTech')}
            onClose={() => setAdding(null)}
          >
            <AddPersonForm
              role={adding}
              onCancel={() => setAdding(null)}
              onDone={() => {
                setAdding(null)
                list.reload()
              }}
            />
          </Drawer>
        )}
      </AnimatePresence>

      {error && <p className="text-status-fail text-xs break-all">{error}</p>}

      {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
      {list.loading && !list.data && <Skeleton className="h-64" />}

      {list.data && people.length === 0 && <EmptyState body={t('equipe.empty')} />}

      {list.data && people.length > 0 && (
        <Chart
          directeur={directeur}
          chefs={chefs}
          techs={techs}
          orphans={orphans}
          selected={selected}
          canEdit={isDirector}
          load={load}
          peak={peak}
          onSelect={setSelected}
          onMove={move}
        />
      )}

      <AnimatePresence>
        {focus && (
          <Drawer label={focus.name} onClose={() => setSelected(null)}>
            <Detail
              person={focus}
              chefs={chefs}
              canEdit={isDirector}
              isSelf={focus.id === user?.id}
              onReload={list.reload}
              onMove={move}
              onError={setError}
            />
          </Drawer>
        )}
      </AnimatePresence>

      <p className="text-ink-faint max-w-[70ch] text-xs">{t('access.enforceNote')}</p>
    </motion.div>
  )
}

// ── the chart ──────────────────────────────────────────────────────────────

function Chart({
  directeur,
  chefs,
  techs,
  orphans,
  selected,
  canEdit,
  load,
  peak,
  onSelect,
  onMove,
}: {
  readonly directeur?: Technician
  readonly chefs: Technician[]
  readonly techs: Technician[]
  readonly orphans: Technician[]
  readonly selected: number | null
  readonly canEdit: boolean
  readonly load: Load
  readonly peak: number
  readonly onSelect: (id: number) => void
  readonly onMove: (personId: number, managerId: number | null) => void
}) {
  const { t } = useI18n()
  // A chef's bar is their crew's output, not their own: a site manager who
  // sends nothing while their six technicians send forty is not idle.
  const teamOf = (chef: Technician) =>
    techs
      .filter((p) => p.manager_id === chef.id)
      .reduce(
        (acc, p) => {
          const s = load.get(p.name.trim().toLowerCase())
          return { count: acc.count + (s?.count ?? 0), flagged: acc.flagged + (s?.flagged ?? 0) }
        },
        { count: 0, flagged: 0 },
      )
  return (
    <div className="overflow-x-auto pb-2">
      {/*
        A key for the one encoded thing on the chart.

        The bar under each name carries two quantities and nothing on the page
        said so — an operator either guessed or ignored it, and an ignored
        encoding is wasted ink. Stated once, quietly, above the chart rather
        than repeated in six tooltips.
      */}
      <div className="text-ink-faint mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.6875rem]">
        <span className="flex items-center gap-1.5">
          <span className="bg-accent h-1 w-6 rounded-full" />
          {t('equipe.legendReports')}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="bg-status-warn h-1 w-3 rounded-full" />
          {t('equipe.legendFlagged')}
        </span>
        {canEdit && <span className="ms-auto">{t('equipe.legendDrag')}</span>}
      </div>

      <div className="flex min-w-max flex-col items-center gap-0">
        {directeur && (
          <div className={cn(chefs.length > 0 && 'org-stem')}>
            <Box
              person={directeur}
              selected={selected === directeur.id}
              onSelect={onSelect}
              onMove={onMove}
              canEdit={canEdit}
              stat={load.get(directeur.name.trim().toLowerCase())}
              peak={peak}
            />
          </div>
        )}

        <div className="org-crew">
          <ul className="org-branch flex flex-nowrap items-start justify-center gap-6">
            {chefs.map((chef) => {
              const crew = techs.filter((p) => p.manager_id === chef.id)
              return (
                <li key={chef.id} className="org-node flex flex-col items-center">
                  <div className={cn(crew.length > 0 && 'org-stem')}>
                    <Box
                      person={chef}
                      selected={selected === chef.id}
                      onSelect={onSelect}
                      onMove={onMove}
                      canEdit={canEdit}
                      stat={teamOf(chef)}
                      peak={Math.max(peak, teamOf(chef).count)}
                      crew={crew.length}
                      dropTarget
                    />
                  </div>
                  <div className="org-crew">
                    {chunk(crew, CREW_PER_ROW).map((row) => (
                      <ul
                        key={row.map((p) => p.id).join('-')}
                        className="org-branch flex items-start justify-center gap-3"
                      >
                        {row.map((p) => (
                          <li key={p.id} className="org-node">
                            <Box
                              person={p}
                              selected={selected === p.id}
                              onSelect={onSelect}
                              onMove={onMove}
                              canEdit={canEdit}
                              stat={load.get(p.name.trim().toLowerCase())}
                              peak={peak}
                              draggable
                            />
                          </li>
                        ))}
                      </ul>
                    ))}
                  </div>
                </li>
              )
            })}
          </ul>
        </div>

        {orphans.length > 0 && (
          <section className="mt-10 flex w-full flex-col items-center gap-3">
            <h2 className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
              {t('equipe.unassigned')}
            </h2>
            {/* Also a drop target, so someone can be pulled back out of a crew
                without hunting for the select in the detail panel. */}
            <DropZone canEdit={canEdit} onDrop={(id) => onMove(id, null)}>
              <ul className="flex flex-wrap justify-center gap-3">
                {orphans.map((p) => (
                  <li key={p.id}>
                    <Box
                      person={p}
                      selected={selected === p.id}
                      onSelect={onSelect}
                      onMove={onMove}
                      canEdit={canEdit}
                      stat={load.get(p.name.trim().toLowerCase())}
                      peak={peak}
                      draggable
                    />
                  </li>
                ))}
              </ul>
            </DropZone>
          </section>
        )}
      </div>
    </div>
  )
}

const DRAG_TYPE = 'application/x-aznet-person'

/** Border of a drop target: hovered wins over selected, both beat the default. */
function dropBorder(over: boolean, selected: boolean): string {
  if (over) return 'border-accent ring-accent ring-2'
  return selected ? 'border-accent' : 'border-line'
}

/**
 * One box. Click selects, drag reassigns.
 *
 * ponytail: native HTML5 drag-and-drop, no dnd library. It does not fire on
 * touch — the `<select>` in the detail panel is the path for phones and for
 * keyboards, and it has to exist regardless because dragging is not a keyboard
 * gesture. Upgrade to @dnd-kit only if touch reordering is actually wanted.
 */
function Box({
  person,
  selected,
  canEdit,
  draggable,
  dropTarget,
  stat,
  peak,
  crew,
  onSelect,
  onMove,
}: {
  readonly person: Technician
  readonly selected: boolean
  readonly canEdit: boolean
  readonly draggable?: boolean
  readonly dropTarget?: boolean
  /**
   * A chef's card shows their crew's summed output, which has no single date or
   * language behind it — hence the optional half. Structurally, a whole
   * `PersonStats` satisfies this, so a technician's card passes one straight in.
   */
  readonly stat?: {
    count: number
    flagged: number
    last?: string | null
    sites?: number
    pctArabic?: number | null
  }
  readonly peak: number
  readonly crew?: number
  readonly onSelect: (id: number) => void
  readonly onMove: (personId: number, managerId: number | null) => void
}) {
  const { t } = useI18n()
  const [over, setOver] = useState(false)
  const [lifting, setLifting] = useState(false)
  const canDrag = canEdit && draggable
  const still = useReducedMotion()
  // A technician's card, i.e. the one whose figures are about one person.
  const isCrewCard = person.role !== 'directeur' && person.role !== 'chef'

  return (
    /*
      `layoutId` is what makes a reassignment visible.
      
      The box is torn out of one chef's crew and re-mounted under another, which
      React renders as an instant jump — the person is simply somewhere else and
      the eye has nothing to follow. With a stable layoutId motion measures the
      old and new rectangles and springs the same element between them, so the
      move is watched rather than inferred. It reads as a move precisely because
      it is animated with the page's own spring (DESIGN.md: stiffness 100,
      damping 20) and only touches transform.
    */
    <motion.div
      layout={!still}
      layoutId={still ? undefined : `org-person-${person.id}`}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
    >
      {/* Native HTML5 drag lives on a plain child: motion owns `onDragStart`
          for its own pointer-drag gesture, and the two signatures do not
          agree. Keeping them on separate elements is cheaper than casting
          around a real type conflict. */}
      <div
        draggable={canDrag}
        onDragStart={(e) => {
          e.dataTransfer.setData(DRAG_TYPE, String(person.id))
          e.dataTransfer.effectAllowed = 'move'
          // Native drag freezes the source element's own repaint the instant
          // dragstart fires — the browser has already snapshotted it for the
          // ghost image and won't apply further style changes to the real DOM
          // node until drop. Setting the state one tick later, after that
          // snapshot is taken, is what makes the gap actually visible while
          // held instead of only flashing in on release.
          setTimeout(() => setLifting(true), 0)
        }}
        onDragEnd={() => setLifting(false)}
        onDragOver={
          canEdit && dropTarget
            ? (e) => {
                // preventDefault is what marks this a valid drop target; without
                // it the browser refuses the drop and nothing happens.
                e.preventDefault()
                e.dataTransfer.dropEffect = 'move'
                setOver(true)
              }
            : undefined
        }
        onDragLeave={() => setOver(false)}
        onDrop={
          canEdit && dropTarget
            ? (e) => {
                e.preventDefault()
                setOver(false)
                const dragged = Number(e.dataTransfer.getData(DRAG_TYPE))
                if (dragged && dragged !== person.id) onMove(dragged, person.id)
              }
            : undefined
        }
        // Only the hovered target lights up — never every valid chef at once.
        // DESIGN.md's Ten Percent Rule: two accented things on screen means one
        // of them is wrong, and a whole row of accent rings finds nothing.
        //
        // While this box is the one being dragged, its own spot turns into an
        // empty dashed gap instead — a slot with nothing in it, the way the
        // rest of the row would actually look with this person lifted out.
        // The browser's native drag ghost is what carries the moving card;
        // this stays put and hollow.
        className={cn(
          'rounded-lg border transition-colors',
          lifting ? 'border-accent bg-accent/5 border-dashed' : dropBorder(over, selected),
        )}
      >
        <button
          type="button"
          onClick={() => onSelect(person.id)}
          aria-pressed={selected}
          /*
            Every card in a band is the same rectangle, whatever its occupant
            has or has not sent. Sizing to content made the chart ragged and,
            worse, made an empty week look like a smaller job: a box's height
            was reading as a second, accidental measure of the person in it.
            Technicians get the taller card because theirs is the one carrying
            per-person figures; a chef's carries a crew total.
          */
          className={cn(
            'bg-surface edge focus-visible:ring-accent flex cursor-pointer flex-col items-start gap-1 rounded-lg px-3 py-2.5 text-start outline-none focus-visible:ring-2',
            isCrewCard ? 'h-32 w-44' : 'h-24 w-44',
            // Depth on hover, not colour: the card is already bordered, and a
            // tint here would compete with the drop-target ring that has to
            // stay the loudest thing on the chart while dragging. Explicit
            // properties — never `transition: all` on a card that also moves
            // under motion's layout animation.
            'shadow-[0_1px_2px_-1px_oklch(0.146_0.008_245/0.08)] transition-[box-shadow,border-color] duration-150',
            'hover:shadow-[0_6px_16px_-8px_oklch(0.146_0.008_245/0.28)]',
            canDrag && 'cursor-grab active:cursor-grabbing',
            lifting && 'bg-transparent opacity-0 shadow-none',
          )}
        >
          <span className="text-ink w-full truncate text-sm font-medium text-balance">
            {person.name}
          </span>
          <span className="flex w-full items-center gap-1.5">
            <span className="text-ink-faint flex-1 truncate text-[0.6875rem] tracking-wide uppercase">
              {t(`equipe.role.${person.role ?? 'tech'}`)}
            </span>
            {/* Which channels reach them, not what their addresses are. The raw
              external_id — a phone number or a Telegram chat id — used to sit on
              every box, which made the chart a wall of digits and pushed the one
              thing a chart is for (who reports to whom) into third place. The
              full identities are one click away in the detail panel. */}
            {person.identities.map((id) => (
              <ChannelIcon
                key={id.id}
                channel={id.channel}
                size={12}
                className={cn('text-ink-faint shrink-0', !id.active && 'opacity-40')}
              />
            ))}
            {person.has_login && (
              <span className="text-ink-faint shrink-0" title={t('equipe.hasLogin')}>
                <KeyIcon size={12} />
                <span className="sr-only">{t('equipe.hasLogin')}</span>
              </span>
            )}
          </span>

          {/*
          Load. A bar plus its own number, never the bar alone: the chart is
          read at a glance for shape and then squinted at for the actual figure,
          and a bar with no value is a shape you cannot act on.

          Flagged reports are drawn as a second segment in the warning colour —
          the Reserved Band Rule's exact sanctioned meaning — and the count is
          in the title text too, so the split never rests on hue.
        */}
          {stat && stat.count > 0 && (
            <span
              className="mt-0.5 flex w-full items-center gap-2"
              title={loadLabel(t, person.name, stat, crew)}
            >
              <span className="bg-line relative h-1 flex-1 overflow-hidden rounded-full">
                <span
                  className="bg-accent absolute inset-y-0 start-0 rounded-full"
                  style={{ inlineSize: `${Math.max(4, (stat.count / peak) * 100)}%` }}
                />
                {stat.flagged > 0 && (
                  <span
                    className="bg-status-warn absolute inset-y-0 start-0 rounded-full"
                    style={{ inlineSize: `${Math.max(2, (stat.flagged / peak) * 100)}%` }}
                  />
                )}
              </span>
              <span className="tabular text-ink-muted text-[0.625rem]">{stat.count}</span>
              <span className="sr-only">{loadLabel(t, person.name, stat, crew)}</span>
            </span>
          )}

          {crew !== undefined && crew > 0 && (
            <span className="text-ink-faint text-[0.625rem]">
              {t('equipe.crewCount', { count: crew })}
            </span>
          )}

          {/*
            The three questions a manager opens this chart with, under the bar:
            when did I last hear from them, how much of it needs checking, and
            which language do they dictate in. `mt-auto` pins the row to the
            bottom of the fixed-height card, so the line is in the same place on
            every technician — a row that floated with content length would be
            read as a fourth, meaningless variable.
          */}
          {isCrewCard && (
            <span className="text-ink-faint mt-auto flex w-full items-center gap-2 text-[0.625rem]">
              <span className="truncate">
                {stat?.last ? t('equipe.lastOn', { date: stat.last }) : t('equipe.neverSent')}
              </span>
              {stat && stat.flagged > 0 && (
                <span className="text-status-warn tabular ms-auto shrink-0">⚑ {stat.flagged}</span>
              )}
              {stat?.pctArabic !== null && stat?.pctArabic !== undefined && (
                <span className={cn('tabular shrink-0', !stat.flagged && 'ms-auto')}>
                  {stat.pctArabic}% {t('equipe.langAr')}
                </span>
              )}
            </span>
          )}
        </button>
      </div>
    </motion.div>
  )
}

/** One sentence carrying everything the bar encodes, for the title and SR text. */
function loadLabel(
  t: (k: string, v?: Record<string, string | number>) => string,
  name: string,
  stat: { count: number; flagged: number },
  crew?: number,
): string {
  const base =
    crew === undefined
      ? t('equipe.loadSelf', { name, count: stat.count })
      : t('equipe.loadTeam', { name, count: stat.count })
  return stat.flagged > 0 ? `${base} — ${t('equipe.loadFlagged', { count: stat.flagged })}` : base
}

function DropZone({
  canEdit,
  onDrop,
  children,
}: {
  readonly canEdit: boolean
  readonly onDrop: (personId: number) => void
  readonly children: React.ReactNode
}) {
  const [over, setOver] = useState(false)
  if (!canEdit) return <>{children}</>
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        const dragged = Number(e.dataTransfer.getData(DRAG_TYPE))
        if (dragged) onDrop(dragged)
      }}
      className={cn(
        'rounded-xl border border-dashed p-3 transition-colors',
        over ? 'border-accent' : 'border-line',
      )}
    >
      {children}
    </div>
  )
}

/**
 * A modal window.
 *
 * A native `<dialog>` opened with `showModal()`, not a div: the platform already
 * gives the focus trap, the Esc key, the inert background and the top-layer
 * stacking that a hand-rolled modal has to re-implement and usually gets wrong
 * for keyboard users. Only the skin is ours.
 *
 * It is also why the "add" forms live here rather than in the page flow — a
 * panel that opens between the intro and the chart pushes the whole org chart
 * down the screen, so pressing "+" appears to move everyone.
 */
function Modal({
  title,
  onClose,
  children,
}: {
  readonly title: string
  readonly onClose: () => void
  readonly children: React.ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)

  // showModal() is imperative — there is no `open modally` attribute, and the
  // `open` attribute alone renders a non-modal dialog with no focus trap.
  // Guarded: under StrictMode the effect runs twice in dev, and a second
  // showModal() on an already-open dialog throws InvalidStateError.
  useEffect(() => {
    if (ref.current && !ref.current.open) ref.current.showModal()
  }, [])

  return (
    <dialog
      ref={ref}
      onCancel={onClose}
      onClose={onClose}
      aria-label={title}
      className="bg-surface border-line text-ink m-auto rounded-xl border p-5 shadow-lg backdrop:bg-slate-950/40 backdrop:backdrop-blur-sm"
    >
      <h2 className="text-ink text-sm font-medium">{title}</h2>
      {children}
    </dialog>
  )
}

/**
 * A panel that slides in from the inline end, over a dimmed page.
 *
 * One component for both "who is this person" and "add a person": they are the
 * same kind of side task, and giving them the same surface means the operator
 * learns one dismissal gesture (backdrop, Esc, or the ✕) instead of two. `end`
 * rather than `right`, so Arabic gets a left-hand drawer for free.
 */
function Drawer({
  label,
  onClose,
  children,
}: {
  readonly label: string
  readonly onClose: () => void
  readonly children: React.ReactNode
}) {
  const { t } = useI18n()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <>
      <motion.div
        className="fixed inset-0 z-40 bg-slate-950/40 backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        onClick={onClose}
        aria-hidden="true"
      />
      <motion.div
        role="dialog"
        aria-label={label}
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', stiffness: 220, damping: 28 }}
        className="border-line bg-surface edge fixed top-0 bottom-0 end-0 z-50 flex w-full max-w-md flex-col gap-6 overflow-y-auto border-s p-5 shadow-[0_16px_40px_-20px_oklch(0.146_0.008_245/0.45)]"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label={t('nav.close')}
          className="text-ink-faint hover:text-ink focus-visible:ring-accent absolute end-4 top-4 cursor-pointer rounded p-1 transition-colors outline-none focus-visible:ring-2"
        >
          <XIcon size={16} />
        </button>
        {children}
      </motion.div>
    </>
  )
}

/** Ask before an irreversible delete. */
function Confirm({
  title,
  body,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  readonly title: string
  readonly body: string
  readonly confirmLabel: string
  readonly onConfirm: () => void
  readonly onCancel: () => void
}) {
  const { t } = useI18n()
  return (
    <Modal title={title} onClose={onCancel}>
      <p className="text-ink-muted mt-2 max-w-[42ch] text-xs leading-relaxed">{body}</p>
      <div className="mt-5 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent cursor-pointer rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2"
        >
          {t('inbox.cancel')}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className="bg-status-fail focus-visible:ring-accent cursor-pointer rounded-md px-3 py-1.5 text-xs text-white transition-opacity outline-none hover:opacity-90 focus-visible:ring-2"
        >
          {confirmLabel}
        </button>
      </div>
    </Modal>
  )
}

// ── the detail panel ───────────────────────────────────────────────────────

/**
 * What one selected person is. Contents follow their role, because the two
 * halves of the merged page answer different questions: an account's panel is
 * "what have they done", a technician's is "how do they reach us and what does
 * the model know about them". Showing a technician the activity blocks would
 * mean three panels that are empty forever — which reads as a broken page, not
 * as "this person never signs in".
 */
function Detail({
  person,
  chefs,
  canEdit,
  isSelf,
  onReload,
  onMove,
  onError,
}: {
  readonly person: Technician
  readonly chefs: Technician[]
  readonly canEdit: boolean
  readonly isSelf: boolean
  readonly onReload: () => void
  readonly onMove: (personId: number, managerId: number | null) => void
  readonly onError: (msg: string) => void
}) {
  const { t } = useI18n()
  const [granting, setGranting] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const isAccount = person.role === 'directeur' || person.role === 'chef'
  // Keyed by id so switching person refetches instead of showing the previous
  // one's history under the new name.
  const hist = useApi(`history:${person.id}`, (s) => api.history(person.id, s))

  const run = (fn: () => Promise<unknown>) => async () => {
    try {
      await fn()
      onReload()
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <motion.section
      key={person.id}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      className="flex flex-col gap-6 pt-2"
    >
      <div className="flex flex-wrap items-center gap-3 pe-8">
        <h2 className="text-ink text-sm font-medium">{person.name}</h2>
        <span className="text-ink-faint text-xs">{t(`equipe.role.${person.role ?? 'tech'}`)}</span>
        {person.email && <span className="text-ink-faint text-xs">{person.email}</span>}

        {canEdit && (
          <span className="ms-auto flex items-center gap-1">
            <button
              type="button"
              onClick={run(() => refreshProfile(person.id))}
              aria-label={`${t('access.regenerate')} ${person.name}`}
              className="text-ink-faint hover:text-ink focus-visible:ring-accent cursor-pointer rounded p-1 transition-colors outline-none focus-visible:ring-2"
            >
              <ArrowsClockwiseIcon size={15} />
            </button>
            {person.has_login && !isSelf && (
              <button
                type="button"
                onClick={run(() => deleteUser(person.id))}
                aria-label={`${t('equipe.revoke')} ${person.name}`}
                className="text-ink-faint hover:text-status-fail focus-visible:ring-accent cursor-pointer rounded p-1 transition-colors outline-none focus-visible:ring-2"
              >
                <UserMinusIcon size={15} />
              </button>
            )}
            {!isSelf && (
              <button
                type="button"
                onClick={() => setConfirming(true)}
                aria-label={`${t('access.removePerson')} ${person.name}`}
                className="text-ink-faint hover:text-status-fail focus-visible:ring-accent cursor-pointer rounded p-1 transition-colors outline-none focus-visible:ring-2"
              >
                <TrashIcon size={15} />
              </button>
            )}
          </span>
        )}
      </div>

      {/* The keyboard and touch path for what drag does with a pointer. Not a
          fallback bolted on: HTML5 DnD fires on neither, so for most of the
          ways this page is reached, this select IS the feature. */}
      {canEdit && !isAccount && (
        <label className="flex max-w-xs flex-col gap-1.5">
          <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
            {t('equipe.chef')}
          </span>
          <select
            value={person.manager_id ?? ''}
            onChange={(e) => onMove(person.id, e.target.value ? Number(e.target.value) : null)}
            className="border-line focus:border-accent focus-visible:ring-accent text-ink bg-canvas cursor-pointer rounded-md border px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-2"
          >
            <option value="">{t('equipe.unassigned')}</option>
            {chefs.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      )}

      <Identities person={person} canEdit={canEdit} onReload={onReload} onError={onError} />

      {!isAccount && <WorkerStats name={person.name} />}

      <div className="flex flex-col gap-2">
        <h3 className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
          {t('equipe.profile')}
        </h3>
        <p className="text-ink-muted max-w-[70ch] text-xs leading-relaxed">
          {person.profile || <span className="text-ink-faint italic">{t('access.noProfile')}</span>}
        </p>
      </div>

      {isAccount && !person.has_login && canEdit && (
        <div className="flex flex-col gap-2">
          <h3 className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
            {t('equipe.access')}
          </h3>
          {granting ? (
            <GrantAccessForm
              name={person.name}
              onDone={() => {
                setGranting(false)
                onReload()
              }}
            />
          ) : (
            <button
              type="button"
              onClick={() => setGranting(true)}
              className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent w-fit cursor-pointer rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2"
            >
              {t('equipe.grant')}
            </button>
          )}
        </div>
      )}

      {isAccount && person.has_login && <HistBlock hist={hist} />}

      {confirming && (
        <Confirm
          title={t('equipe.confirmDelete')}
          body={t('equipe.confirmDeleteBody', { name: person.name })}
          confirmLabel={t('access.removePerson')}
          onCancel={() => setConfirming(false)}
          onConfirm={() => {
            setConfirming(false)
            void run(() => deletePerson(person.id))()
          }}
        />
      )}
    </motion.section>
  )
}

function Identities({
  person,
  canEdit,
  onReload,
  onError,
}: {
  readonly person: Technician
  readonly canEdit: boolean
  readonly onReload: () => void
  readonly onError: (msg: string) => void
}) {
  const { t } = useI18n()
  const [channel, setChannel] = useState<(typeof CHANNELS)[number]>('whatsapp')
  const [externalId, setExternalId] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!externalId.trim()) return
    setBusy(true)
    try {
      await addTechnician({ channel, external_id: externalId.trim(), name: person.name })
      setExternalId('')
      onReload()
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
        {t('equipe.channels')}
      </h3>

      {person.identities.length === 0 ? (
        <p className="text-ink-faint text-xs italic">{t('equipe.noChannel')}</p>
      ) : (
        <ul className="flex flex-wrap gap-1.5">
          {person.identities.map((id) => (
            <li
              key={id.id}
              className={cn(
                'border-line text-ink-muted flex items-center gap-1.5 rounded-full border py-0.5 ps-2 pe-1 text-xs',
                !id.active && 'opacity-50',
              )}
            >
              <ChannelIcon channel={id.channel} size={12} />
              <span className="tabular">{id.external_id}</span>
              <span className="text-ink-faint text-[0.625rem]">
                {id.channel === 'telegram' ? t('access.chatId') : t('access.phone')}
              </span>
              {canEdit && (
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      await deleteTechnician(id.id)
                      onReload()
                    } catch (err) {
                      onError(err instanceof Error ? err.message : String(err))
                    }
                  }}
                  aria-label={`${t('access.remove')} ${id.channel} ${id.external_id}`}
                  className="text-ink-faint hover:text-status-fail focus-visible:ring-accent cursor-pointer rounded p-0.5 transition-colors outline-none focus-visible:ring-2"
                >
                  <TrashIcon size={12} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {canEdit && (
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <fieldset className="border-line m-0 flex rounded-md border p-0.5">
            <legend className="sr-only">{t('inbox.channel')}</legend>
            {CHANNELS.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setChannel(c)}
                aria-pressed={channel === c}
                className={cn(
                  'focus-visible:ring-accent flex cursor-pointer items-center gap-1.5 rounded px-2.5 py-1 text-xs capitalize transition-colors outline-none focus-visible:ring-2',
                  channel === c
                    ? 'bg-slate-100 text-ink dark:bg-slate-850'
                    : 'text-ink-faint hover:text-ink',
                )}
              >
                <ChannelIcon channel={c} size={13} />
                {c}
              </button>
            ))}
          </fieldset>

          <label className="flex min-w-40 flex-col gap-1.5">
            <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
              {channel === 'telegram' ? t('access.chatId') : t('access.phone')}
            </span>
            <input
              value={externalId}
              onChange={(e) => setExternalId(e.target.value)}
              placeholder={channel === 'telegram' ? '123456789' : '2126…'}
              inputMode="numeric"
              className="border-line focus:border-accent focus-visible:ring-accent text-ink bg-canvas placeholder:text-ink-faint rounded-md border px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-2"
            />
          </label>

          <button
            type="submit"
            disabled={busy || !externalId.trim()}
            className={cn(
              'focus-visible:ring-accent flex items-center gap-2 rounded-md px-3.5 py-2 text-sm transition-transform outline-none focus-visible:ring-2 active:translate-y-px',
              busy || !externalId.trim()
                ? 'border-line text-ink-faint cursor-not-allowed border'
                : 'bg-accent cursor-pointer text-white',
            )}
          >
            <PlusIcon size={14} weight="bold" />
            {t('access.add')}
          </button>
        </form>
      )}
    </div>
  )
}

/**
 * What the worker actually did, from their own rows in the Sheet.
 *
 * The language split reads the raw transcript (`rapport_complet`), not the
 * French `resume` — the point is "how do they dictate", and that is only in
 * the original. Script-based detection: Arabic letters count as darija, Latin
 * as French. Darija written in latin letters (arabizi) reads as French here;
 * that is a real limit, and the label admits it.
 */
function WorkerStats({ name }: { readonly name: string }) {
  const { t } = useI18n()
  const reports = useApi('reports', api.reports)

  const stats = useMemo(
    () =>
      statsOf(
        (reports.data?.reports ?? []).filter(
          (r) => (r.technicien ?? '').trim().toLowerCase() === name.trim().toLowerCase(),
        ),
      ),
    [reports.data, name],
  )

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
        {t('equipe.stats')}
      </h3>
      {stats.count === 0 ? (
        <p className="text-ink-faint text-xs italic">{t('equipe.noActivity')}</p>
      ) : (
        <>
          <ul className="divide-line flex flex-col divide-y">
            <Row label={t('equipe.messages')} value={stats.count} />
            <Row label={t('equipe.lastReport')} value={stats.last ?? t('equipe.neverSent')} />
            <Row label={t('equipe.sites')} value={stats.sites} />
            <Row label={t('equipe.flagged')} value={stats.flagged} tone="warn" />
            <Row label={t('metric.goulottes')} value={`${stats.goulottes} m`} />
            <Row label={t('metric.cables')} value={`${stats.cables} m`} />
            <Row label={t('metric.bureaux')} value={stats.bureaux} />
            <Row label={t('metric.panneaux')} value={stats.panneaux} />
          </ul>

          <div className="flex flex-col gap-2 pt-2">
            <h3 className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
              {t('equipe.lang')}
            </h3>
            <LangDonut pct={stats.pctArabic} />
          </div>
        </>
      )}
    </div>
  )
}

function Row({
  label,
  value,
  tone,
}: {
  readonly label: string
  readonly value: string | number
  readonly tone?: 'warn'
}) {
  return (
    <li className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="text-ink-muted text-xs">{label}</span>
      <span className={cn('tabular text-sm', tone === 'warn' ? 'text-status-warn' : 'text-ink')}>
        {value}
      </span>
    </li>
  )
}

/**
 * The darija/French split as one ring.
 *
 * A percentage pair is two numbers the reader has to hold and compare; a ring
 * is the comparison itself. Hand-built SVG, per the no-Recharts rule — a single
 * `stroke-dasharray` on a circle is the whole chart, and the numbers stay in the
 * middle and in the legend so nothing here rests on colour alone.
 */
function LangDonut({ pct }: { readonly pct: number | null }) {
  const { t } = useI18n()
  const still = useReducedMotion()
  if (pct === null) return <p className="text-ink-faint text-xs italic">{t('equipe.langUnknown')}</p>

  // `pathLength={100}` re-scales the dash units, so the dasharray reads literally
  // as "percent, rest" whatever the geometry is. The radius therefore only has
  // to make the ring fit: half the box, less half a stroke on each side, or the
  // circle is drawn outside the viewBox and clipped into arcs.
  const SIZE = 84
  const STROKE = 9
  const C = SIZE / 2
  const R = (SIZE - STROKE) / 2

  return (
    <div className="flex items-center gap-4">
      {/* -90deg so the arc starts at twelve o'clock rather than at three. */}
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="presentation">
        <g transform={`rotate(-90 ${C} ${C})`} fill="none" strokeWidth={STROKE}>
          {/* French is the full ring under the darija arc — a second tint of the
              accent rather than a second hue, because the status band is
              reserved for pipeline state and a language is not one. */}
          <circle cx={C} cy={C} r={R} className="stroke-accent-400/45" />
          <motion.circle
            cx={C}
            cy={C}
            r={R}
            pathLength={100}
            strokeLinecap="round"
            className="stroke-accent"
            initial={still ? false : { strokeDasharray: `0 100` }}
            animate={{ strokeDasharray: `${pct} ${100 - pct}` }}
            transition={{ type: 'spring', stiffness: 100, damping: 20 }}
          />
        </g>
        <text
          x={C}
          y={C}
          textAnchor="middle"
          dominantBaseline="central"
          className="fill-ink tabular text-[0.8125rem]"
        >
          {pct}%
        </text>
      </svg>

      <ul className="flex flex-col gap-1.5 text-xs">
        <li className="flex items-center gap-2">
          <span className="bg-accent size-2 shrink-0 rounded-full" />
          <span className="text-ink-muted">
            <span className="tabular text-ink">{pct}%</span> {t('equipe.langAr')}
          </span>
        </li>
        <li className="flex items-center gap-2">
          <span className="bg-accent-400/45 size-2 shrink-0 rounded-full" />
          <span className="text-ink-muted">
            <span className="tabular text-ink">{100 - pct}%</span> {t('equipe.langFr')}
          </span>
        </li>
      </ul>
    </div>
  )
}

/**
 * The "+": a name, and the channels that reach them.
 *
 * The channels are optional but they are here, not one click later in the
 * detail panel: a technician with no channel cannot send anything, so creating
 * one and then having to remember a second step produced people who existed on
 * the chart and nowhere in the pipeline. Credentials stay a separate step —
 * those are for chefs who sign in, which is a different decision.
 */
function AddPersonForm({
  role,
  onDone,
  onCancel,
}: {
  readonly role: 'chef' | 'tech'
  readonly onDone: () => void
  readonly onCancel: () => void
}) {
  const { t } = useI18n()
  const [name, setName] = useState('')
  const [ids, setIds] = useState<Record<(typeof CHANNELS)[number], string>>({
    telegram: '',
    whatsapp: '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const clean = name.trim()
    if (!clean) return
    setBusy(true)
    setError(null)
    try {
      await addPerson({ name: clean, role })
      // Sequential, and after the person exists: `upsert_technician` matches on
      // name, so a channel written before the person would create a second row
      // for the same human — the exact split the accounts fold was undoing.
      for (const channel of CHANNELS) {
        const external = ids[channel].trim()
        if (external) await addTechnician({ channel, external_id: external, name: clean })
      }
      setName('')
      setIds({ telegram: '', whatsapp: '' })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4 pt-2">
      <h2 className="text-ink text-sm font-medium">
        {t(role === 'chef' ? 'equipe.addChef' : 'equipe.addTech')}
      </h2>
      <p className="text-ink-faint text-xs leading-relaxed">
        {t(role === 'chef' ? 'equipe.addChefNote' : 'equipe.addTechNote')}
      </p>

      <label className="flex flex-col gap-1.5">
        <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
          {t('team.name')}
        </span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          autoFocus
          className="border-line focus:border-accent focus-visible:ring-accent text-ink bg-canvas rounded-md border px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-2"
        />
      </label>
      {CHANNELS.map((channel) => (
        <label key={channel} className="flex flex-col gap-1.5">
          <span className="text-ink-faint flex items-center gap-1.5 text-[0.6875rem] tracking-wide uppercase">
            <ChannelIcon channel={channel} size={12} />
            {channel} · {t(channel === 'telegram' ? 'access.chatId' : 'access.phone')}
            <span className="text-ink-faint normal-case">({t('equipe.optional')})</span>
          </span>
          <input
            value={ids[channel]}
            onChange={(e) => setIds((v) => ({ ...v, [channel]: e.target.value }))}
            placeholder={channel === 'telegram' ? '123456789' : '2126…'}
            inputMode="numeric"
            className="border-line focus:border-accent focus-visible:ring-accent text-ink bg-canvas placeholder:text-ink-faint rounded-md border px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-2"
          />
        </label>
      ))}

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent cursor-pointer rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2"
        >
          {t('inbox.cancel')}
        </button>
        <button
          type="submit"
          disabled={busy || !name.trim()}
          className="bg-accent focus-visible:ring-accent cursor-pointer rounded-md px-3.5 py-1.5 text-xs text-white transition-transform outline-none active:translate-y-px focus-visible:ring-2 disabled:opacity-50"
        >
          {t('equipe.create')}
        </button>
      </div>
      {error && <p className="text-status-fail w-full text-xs break-all">{error}</p>}
    </form>
  )
}
