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
import { cn } from '@/lib/utils'

/** Icon + colour per notification kind. `report` is the fallback. */
const KIND_DOT: Record<NotificationItem['kind'], { Icon: typeof BellIcon; cls: string }> = {
  error: { Icon: WarningCircleIcon, cls: 'text-status-fail' },
  review: { Icon: WarningIcon, cls: 'text-status-warn' },
  reminder: { Icon: LightningIcon, cls: 'text-accent' },
  report: { Icon: BellIcon, cls: 'text-status-ok' },
}

/**
 * The per-account bell. Rows are created by the API (own team's new reports,
 * rows flagged for review, Sheet write failures, due task reminders); only the
 * signed-in person's own rows are ever shown here.
 */
export function Bell({ onNavigate }: { readonly onNavigate: (r: Route) => void }) {
  const { t, locale } = useI18n()
  const { settings } = useSettings()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  // Polls on the refresh interval so a report landing while the dashboard is
  // open rings within seconds; the module cache makes the count instant on remount.
  const list = useApi('notifications', api.notifications, settings.refreshMs)

  const items = list.data?.items ?? []
  const unread = list.data?.unread ?? 0

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
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            transition={{ duration: 0.12 }}
            className="border-line bg-surface edge absolute end-0 top-full z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border shadow-xl shadow-black/5"
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
