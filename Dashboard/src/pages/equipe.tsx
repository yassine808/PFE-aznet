import { useState } from 'react'
import { motion } from 'motion/react'
import {
  ArrowsClockwiseIcon,
  PlusIcon,
  TrashIcon,
  UserMinusIcon,
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
  const [adding, setAdding] = useState(false)
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
          <button
            type="button"
            onClick={() => setAdding((v) => !v)}
            aria-expanded={adding}
            className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent ms-auto flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors outline-none focus-visible:ring-2"
          >
            <PlusIcon size={13} weight="bold" />
            {t('equipe.addChef')}
          </button>
        )}
      </div>

      {adding && isDirector && (
        <AddChefForm
          onDone={() => {
            setAdding(false)
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

      {focus && (
        <Detail
          person={focus}
          chefs={chefs}
          canEdit={isDirector}
          isSelf={focus.id === user?.id}
          onReload={list.reload}
          onMove={move}
          onError={setError}
        />
      )}

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
      className={cn(
        'rounded-xl border transition-colors',
        over ? 'border-accent ring-accent ring-2' : selected ? 'border-accent' : 'border-line',
      )}
    >
      <button
        type="button"
        onClick={() => onSelect(person.id)}
        aria-pressed={selected}
        className={cn(
          'bg-surface edge focus-visible:ring-accent flex w-44 cursor-pointer flex-col items-start gap-1 rounded-xl px-3.5 py-3 text-start outline-none focus-visible:ring-2',
          canDrag && 'cursor-grab active:cursor-grabbing',
        )}
      >
        <span className="text-ink w-full truncate text-sm font-medium">{person.name}</span>
        <span className="text-ink-faint text-[0.6875rem] tracking-wide uppercase">
          {t(`equipe.role.${person.role ?? 'tech'}`)}
        </span>
        {/* Every identity present, channel-labelled. WhatsApp's external_id is a
            phone number; Telegram's is a chat id, which is why the badge always
            carries its icon rather than being presented as "the phone". */}
        {person.identities.length > 0 && (
          <span className="flex flex-wrap items-center gap-1">
            {person.identities.map((id) => (
              <span
                key={id.id}
                className={cn(
                  'border-line text-ink-muted flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[0.625rem]',
                  !id.active && 'opacity-50',
                )}
              >
                <ChannelIcon channel={id.channel} size={10} />
                <span className="tabular">{id.external_id}</span>
              </span>
            ))}
          </span>
        )}
        {person.has_login && (
          <span className="text-ink-faint text-[0.625rem]">{t('equipe.hasLogin')}</span>
        )}
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
      className="border-line bg-surface edge flex flex-col gap-6 rounded-xl border p-5"
    >
      <div className="flex flex-wrap items-center gap-3">
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

/** The "+": a name, nothing else. Credentials are a separate, later step. */
function AddChefForm({ onDone }: { readonly onDone: () => void }) {
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
      await addPerson({ name: name.trim(), role: 'chef' })
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
      <p className="text-ink-faint w-full text-xs">{t('equipe.addChefNote')}</p>
      {error && <p className="text-status-fail w-full text-xs break-all">{error}</p>}
    </form>
  )
}
