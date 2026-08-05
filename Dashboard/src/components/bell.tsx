import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  BellIcon,
  CheckIcon,
  LightningIcon,
  WarningCircleIcon,
  WarningIcon,
} from '@phosphor-icons/react'
import { api, markNotificationsRead, useApi, type NotificationItem } from '@/lib/api'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'
import { ROUTES, type Route } from '@/lib/router'
import { useAuth } from '@/lib/auth'
import { chime } from '@/lib/alarm'
import { useToast, type ToastTone } from '@/lib/toast'
import { cn } from '@/lib/utils'

/** Icon + colour per notification kind. `report` is the fallback. */
const KIND_DOT: Record<NotificationItem['kind'], { Icon: typeof BellIcon; cls: string }> = {
  error: { Icon: WarningCircleIcon, cls: 'text-status-fail' },
  review: { Icon: WarningIcon, cls: 'text-status-warn' },
  reminder: { Icon: LightningIcon, cls: 'text-accent' },
  report: { Icon: BellIcon, cls: 'text-status-ok' },
}

/** The bell's own vocabulary, mapped onto the toast's four tones. */
const KIND_TONE: Record<NotificationItem['kind'], ToastTone> = {
  error: 'error',
  review: 'warn',
  reminder: 'info',
  report: 'success',
}

/**
 * Highest notification id already announced, shared by every Bell on the page.
 *
 * The shell mounts two — one in the mobile bar, one in the rail — and CSS
 * hides the wrong one rather than unmounting it, so both run this effect on
 * the same polled data. A per-component ref would ring twice; module state
 * means whichever renders first claims the row and the other sees nothing new.
 *
 * `null` until the first response: on a fresh page load every existing row is
 * "new", and announcing a week of history as it arrives is how a notification
 * system teaches people to ignore it.
 */
let announced: number | null = null

/**
 * The per-account bell. Rows are created by the API (own team's new reports,
 * rows flagged for review, Sheet write failures, due task reminders); only the
 * signed-in person's own rows are ever shown here.
 */
export function Bell({
  onNavigate,
  placement = 'down',
}: {
  readonly onNavigate: (r: Route) => void
  /**
   * Which way the panel opens. The rail's bell sits a few centimetres above the
   * bottom of a full-height sticky column, so a panel dropping from `top-full`
   * rendered below the fold — open, correct, and entirely off-screen. `up` is
   * not a preference there, it is the only direction with room.
   */
  readonly placement?: 'down' | 'up'
}) {
  const { t, locale } = useI18n()
  const { settings } = useSettings()
  const { user } = useAuth()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  // Polls on the refresh interval so a report landing while the dashboard is
  // open rings within seconds; the module cache makes the count instant on remount.
  const list = useApi('notifications', api.notifications, settings.refreshMs)

  const items = list.data?.items ?? []
  const unread = list.data?.unread ?? 0
  const up = placement === 'up'

  // `announced` outlives a sign-out, and notification ids are one global
  // sequence — so the next account to use this browser would start behind a
  // stranger's high-water mark and hear nothing until it caught up.
  useEffect(() => {
    announced = null
  }, [user?.id])

  // Anything that arrived since the last poll gets a chime and a toast, oldest
  // first so the stack reads top-down in the order things happened.
  useEffect(() => {
    if (!list.data) return
    const newest = items.reduce((max, n) => Math.max(max, n.id), 0)
    if (announced === null) {
      announced = newest // first load: catch up silently
      return
    }
    if (newest <= announced) return
    const fresh = items.filter((n) => n.id > (announced ?? 0)).sort((a, b) => a.id - b.id)
    announced = newest
    if (fresh.length === 0) return
    chime()
    for (const n of fresh) {
      const route = n.route?.replace(/^#\//, '')
      toast({
        tone: KIND_TONE[n.kind] ?? 'info',
        title: n.title,
        body: n.body ?? undefined,
        onOpen:
          route && (ROUTES as readonly string[]).includes(route)
            ? () => onNavigate(route as Route)
            : undefined,
      })
    }
  }, [list.data, items, toast, onNavigate])

  // Click outside and Escape both close the panel, so one gesture or one key
  // backs out — same contract as the mobile drawer.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  const openNotification = async (n: NotificationItem) => {
    setOpen(false)
    if (n.route && (ROUTES as readonly string[]).includes(n.route.replace(/^#\//, ''))) {
      onNavigate(n.route.replace(/^#\//, '') as Route)
    }
    if (n.read_at) return
    try {
      await markNotificationsRead([n.id])
      list.reload()
    } catch {
      /* the bell refreshes on its own interval; a failed read is not an error state */
    }
  }

  const markAll = async () => {
    setBusy(true)
    try {
      await markNotificationsRead()
      list.reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div ref={wrap} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={t('bell.aria', { n: unread })}
        aria-expanded={open}
        aria-controls="bell-panel"
        className="border-line text-ink-muted hover:text-ink relative cursor-pointer rounded-md border p-1.5 transition-colors active:translate-y-px"
      >
        <BellIcon size={15} />
        {unread > 0 && (
          <span className="bg-accent absolute -top-1 -end-1 flex min-w-4 items-center justify-center rounded-full px-1 text-[0.625rem] leading-4 font-semibold text-white tabular">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            id="bell-panel"
            initial={{ opacity: 0, y: up ? -6 : 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: up ? -6 : 6 }}
            transition={{ duration: 0.12 }}
            className={cn(
              'border-line bg-surface edge absolute z-50 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border shadow-xl shadow-black/5',
              // Both axes hang off `placement`, because the rail's bell is
              // cornered on both. Upward is the only direction with vertical
              // room; `start-0` is the only direction with horizontal room —
              // the panel is 320px wide inside a 240px rail, so anchoring its
              // *end* to the button pushed 80px of it off the screen edge.
              // Logical, not `left`: in Arabic the rail is on the other side
              // and the overflow has to go the other way with it.
              up ? 'bottom-full mb-2 start-0' : 'top-full mt-2 end-0',
            )}
          >
            <div className="border-line flex items-center justify-between gap-2 border-b px-3 py-2">
              <p className="text-ink text-sm font-medium">{t('bell.title')}</p>
              {unread > 0 && (
                <button
                  type="button"
                  onClick={markAll}
                  disabled={busy}
                  className="text-ink-muted hover:text-ink focus-visible:ring-accent flex cursor-pointer items-center gap-1 rounded px-1.5 py-0.5 text-xs transition-colors outline-none focus-visible:ring-2 disabled:opacity-50"
                >
                  <CheckIcon size={12} />
                  {t('bell.markAll')}
                </button>
              )}
            </div>

            {items.length === 0 && (
              <p className="text-ink-faint px-3 py-6 text-center text-xs">{t('bell.empty')}</p>
            )}

            {items.length > 0 && (
              <ul className="max-h-80 overflow-y-auto">
                {items.map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      onClick={() => void openNotification(n)}
                      className={cn(
                        'hover:bg-slate-50 flex w-full cursor-pointer items-start gap-2.5 px-3 py-2.5 text-start transition-colors dark:hover:bg-slate-850',
                        n.read_at ? 'opacity-55' : '',
                      )}
                    >
                      <KindDot kind={n.kind} />
                      <span className="min-w-0 flex-1">
                        <span className="text-ink block truncate text-xs font-medium">{n.title}</span>
                        {n.body && (
                          <span className="text-ink-faint line-clamp-2 block text-[0.6875rem]">
                            {n.body}
                          </span>
                        )}
                        <span className="text-ink-faint mt-0.5 block text-[0.625rem] tabular">
                          {new Date(n.created_at).toLocaleString(locale, {
                            dateStyle: 'short',
                            timeStyle: 'short',
                            hour12: settings.timeFormat === '12h',
                          })}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function KindDot({ kind }: { readonly kind: NotificationItem['kind'] }) {
  const { Icon, cls } = KIND_DOT[kind] ?? KIND_DOT.report
  return <Icon size={14} weight="fill" className={cn('mt-0.5 shrink-0', cls)} />
}
