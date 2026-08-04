import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
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
  type Technician,
} from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useI18n } from '@/lib/i18n'
import { isFlagged } from '@/lib/metrics'
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

export function EquipePage() {
  const { t } = useI18n()
  const { user } = useAuth()
  const list = useApi('technicians', api.technicians)

  const [selected, setSelected] = useState<number | null>(null)
  const [adding, setAdding] = useState<'chef' | 'tech' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const isDirector = user?.role === 'directeur'
  const people = list.data?.technicians ?? []

  const directeur = people.find((p) => p.role === 'directeur')
  const chefs = people.filter((p) => p.role === 'chef')
  const techs = people.filter((p) => p.role !== 'directeur' && p.role !== 'chef')
  // Unassigned techs get their own column rather than being dropped: a colleague
  // nobody owns is exactly the thing this page exists to make visible.
  const orphans = techs.filter((p) => !p.manager_id || !chefs.some((c) => c.id === p.manager_id))

  const focus = people.find((p) => p.id === selected) ?? null

  // Escape closes the detail panel, matching the mobile nav drawer's affordance.
  useEffect(() => {
    if (!focus) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setSelected(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [focus])

  const guard = (fn: () => Promise<unknown>) => async () => {
    setError(null)
    try {
      await fn()
      list.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const move = (personId: number, managerId: number | null) =>
    guard(() => setManager(personId, managerId))()

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

      {adding && isDirector && (
        <AddPersonForm
          role={adding}
          onDone={() => {
            setAdding(null)
            list.reload()
          }}
        />
      )}

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
          onSelect={setSelected}
          onMove={move}
        />
      )}

      <AnimatePresence>
        {focus && (
          <motion.div
            className="fixed inset-0 z-40 bg-slate-950/40 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={() => setSelected(null)}
            aria-hidden="true"
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {focus && (
          <motion.div
            role="dialog"
            aria-label={focus.name}
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 220, damping: 28 }}
            className="border-line bg-surface edge fixed top-0 bottom-0 end-0 z-50 flex w-full max-w-md flex-col gap-6 overflow-y-auto border-s p-5 shadow-[0_16px_40px_-20px_oklch(0.146_0.008_245/0.45)]"
          >
            <button
              type="button"
              onClick={() => setSelected(null)}
              aria-label={t('nav.close')}
              className="text-ink-faint hover:text-ink focus-visible:ring-accent absolute end-4 top-4 cursor-pointer rounded p-1 transition-colors outline-none focus-visible:ring-2"
            >
              <XIcon size={16} />
            </button>

            <Detail
              person={focus}
              chefs={chefs}
              canEdit={isDirector}
              isSelf={focus.id === user?.id}
              onReload={list.reload}
              onMove={move}
              onError={setError}
            />
          </motion.div>
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
  onSelect,
  onMove,
}: {
  readonly directeur?: Technician
  readonly chefs: Technician[]
  readonly techs: Technician[]
  readonly orphans: Technician[]
  readonly selected: number | null
  readonly canEdit: boolean
  readonly onSelect: (id: number) => void
  readonly onMove: (personId: number, managerId: number | null) => void
}) {
  const { t } = useI18n()
  return (
    <div className="overflow-x-auto pb-2">
      <div className="flex min-w-max flex-col items-center gap-0">
        {directeur && (
          <div className={cn(chefs.length > 0 && 'org-stem')}>
            <Box
              person={directeur}
              selected={selected === directeur.id}
              onSelect={onSelect}
              onMove={onMove}
              canEdit={canEdit}
            />
          </div>
        )}

        <ul className="org-branch flex items-start justify-center gap-6">
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
                    dropTarget
                  />
                </div>
                <ul className="org-branch flex items-start justify-center gap-3">
                  {crew.map((p) => (
                    <li key={p.id} className="org-node">
                      <Box
                        person={p}
                        selected={selected === p.id}
                        onSelect={onSelect}
                        onMove={onMove}
                        canEdit={canEdit}
                        draggable
                      />
                    </li>
                  ))}
                </ul>
              </li>
            )
          })}
        </ul>

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
  onSelect,
  onMove,
}: {
  readonly person: Technician
  readonly selected: boolean
  readonly canEdit: boolean
  readonly draggable?: boolean
  readonly dropTarget?: boolean
  readonly onSelect: (id: number) => void
  readonly onMove: (personId: number, managerId: number | null) => void
}) {
  const { t } = useI18n()
  const [over, setOver] = useState(false)
  const canDrag = canEdit && draggable

  return (
    <div
      draggable={canDrag}
      onDragStart={(e) => {
        e.dataTransfer.setData(DRAG_TYPE, String(person.id))
        e.dataTransfer.effectAllowed = 'move'
      }}
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
      className={cn('rounded-lg border transition-colors', dropBorder(over, selected))}
    >
      <button
        type="button"
        onClick={() => onSelect(person.id)}
        aria-pressed={selected}
        className={cn(
          'bg-surface edge focus-visible:ring-accent flex w-40 cursor-pointer flex-col items-start gap-1 rounded-lg px-3 py-2.5 text-start outline-none focus-visible:ring-2',
          canDrag && 'cursor-grab active:cursor-grabbing',
        )}
      >
        <span className="text-ink w-full truncate text-sm font-medium">{person.name}</span>
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
      </button>
    </div>
  )
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
                onClick={run(() => deletePerson(person.id))}
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

  const stats = useMemo(() => {
    const rows = (reports.data?.reports ?? []).filter(
      (r) => (r.technicien ?? '').trim() === name.trim(),
    )
    let arabic = 0
    let latin = 0
    for (const r of rows) {
      const text = (r.rapport_complet ?? '').replace(/\s+/g, '')
      for (const ch of text) {
        const code = ch.codePointAt(0) ?? 0
        if (code >= 0x0600 && code <= 0x06ff) arabic += 1
        else if (/[a-zA-ZàâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ]/.test(ch)) latin += 1
      }
    }
    const total = arabic + latin
    return {
      count: rows.length,
      flagged: rows.filter((r) => isFlagged(r.flag_review)).length,
      pctArabic: total === 0 ? null : Math.round((arabic / total) * 100),
    }
  }, [reports.data, name])

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
        {t('equipe.stats')}
      </h3>
      {stats.count === 0 ? (
        <p className="text-ink-faint text-xs italic">{t('equipe.noActivity')}</p>
      ) : (
        <ul className="divide-line flex flex-col divide-y">
          <li className="flex items-baseline justify-between gap-4 py-1.5">
            <span className="text-ink-muted text-xs">{t('equipe.messages')}</span>
            <span className="tabular text-ink text-sm">{stats.count}</span>
          </li>
          <li className="flex items-baseline justify-between gap-4 py-1.5">
            <span className="text-ink-muted text-xs">{t('equipe.lang')}</span>
            <span className="tabular text-ink text-sm">
              {stats.pctArabic === null
                ? t('equipe.langUnknown')
                : `${stats.pctArabic}% ${t('equipe.langAr')} / ${100 - stats.pctArabic}% ${t('equipe.langFr')}`}
            </span>
          </li>
          <li className="flex items-baseline justify-between gap-4 py-1.5">
            <span className="text-ink-muted text-xs">{t('equipe.flagged')}</span>
            <span className="tabular text-status-warn text-sm">{stats.flagged}</span>
          </li>
        </ul>
      )}
    </div>
  )
}

/** The "+": a name, nothing else. Credentials are a separate, later step. */
function AddPersonForm({
  role,
  onDone,
}: {
  readonly role: 'chef' | 'tech'
  readonly onDone: () => void
}) {
  const { t } = useI18n()
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      await addPerson({ name: name.trim(), role })
      setName('')
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={submit}
      className="border-line bg-surface edge flex flex-wrap items-end gap-4 rounded-xl border p-5"
    >
      <label className="flex min-w-48 flex-col gap-1.5">
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
      <button
        type="submit"
        disabled={busy || !name.trim()}
        className="bg-accent focus-visible:ring-accent cursor-pointer rounded-md px-3.5 py-2 text-sm text-white transition-transform outline-none active:translate-y-px focus-visible:ring-2 disabled:opacity-50"
      >
        {t('equipe.create')}
      </button>
      <p className="text-ink-faint w-full text-xs">
        {t(role === 'chef' ? 'equipe.addChefNote' : 'equipe.addTechNote')}
      </p>
      {error && <p className="text-status-fail w-full text-xs break-all">{error}</p>}
    </form>
  )
}
