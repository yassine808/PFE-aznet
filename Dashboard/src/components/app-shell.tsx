import { useEffect, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import {
  ListIcon,
  MagnifyingGlassIcon,
  MoonIcon,
  SignOutIcon,
  SunIcon,
  XIcon,
} from '@phosphor-icons/react'
import { LOCALES, LOCALE_LABEL, useI18n, type Locale } from '@/lib/i18n'
import { useTheme } from '@/lib/theme'
import { useAuth } from '@/lib/auth'
import { ServerStatus } from '@/components/server-status'
import { SettingsPanel } from '@/components/settings-panel'
import { Bell } from '@/components/bell'
import { CommandPalette, useCommandPalette } from '@/components/command-palette'
import { NAV, SYSTEM_NAV, navItem } from '@/lib/nav'
import { useOps } from '@/lib/ops-context'
import { cn } from '@/lib/utils'
import type { Route } from '@/lib/router'

export function AppShell({
  route,
  onNavigate,
  children,
}: {
  readonly route: Route
  readonly onNavigate: (r: Route) => void
  readonly children: ReactNode
}) {
  const { t, locale, setLocale } = useI18n()
  const { theme, toggle } = useTheme()
  const [cmdOpen, setCmdOpen] = useCommandPalette()
  const [drawer, setDrawer] = useState(false)

  // A route change closes the drawer: on a phone the destination has to be
  // visible immediately, not behind the panel that was just tapped.
  useEffect(() => setDrawer(false), [route])

  // Escape closes the drawer as well, so one key backs out of any overlay.
  useEffect(() => {
    if (!drawer) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setDrawer(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawer])

  const current = navItem(route)

  const go = (r: Route) => {
    onNavigate(r)
    setDrawer(false)
  }

  return (
    <div className="min-h-[100dvh] md:grid md:grid-cols-[15rem_1fr]">
      {/* First tab stop on the page: ten nav buttons is exactly the case skip links exist for. */}
      <a
        href="#main"
        className="bg-surface text-ink border-line sr-only rounded-md border px-4 py-2 text-sm focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-[60]"
      >
        {t('nav.skipToContent')}
      </a>

      {/* Mobile bar. Under md the rail is a drawer, so the page starts at the content
          instead of ten links the reader has to scroll past every single time. */}
      <div className="border-line bg-surface/85 edge sticky top-0 z-30 flex items-center gap-3 border-b px-4 py-3 backdrop-blur-xl md:hidden">
        <button
          type="button"
          onClick={() => setDrawer(true)}
          aria-label={t('nav.open')}
          aria-expanded={drawer}
          aria-controls="nav-rail"
          className="border-line text-ink-muted hover:text-ink -ms-1 flex size-11 cursor-pointer items-center justify-center rounded-md border transition-colors active:translate-y-px"
        >
          <ListIcon size={18} />
        </button>

        <p className="text-ink min-w-0 flex-1 truncate text-sm font-medium">
          {current ? t(current.labelKey) : t('app.name')}
        </p>

        <Bell onNavigate={onNavigate} />

        <button
          type="button"
          onClick={() => setCmdOpen(true)}
          aria-label={t('cmd.open')}
          className="border-line text-ink-muted hover:text-ink flex size-11 cursor-pointer items-center justify-center rounded-md border transition-colors active:translate-y-px"
        >
          <MagnifyingGlassIcon size={18} />
        </button>
      </div>

      {/* Backdrop for the mobile drawer only; on md+ the rail is permanent. */}
      <AnimatePresence>
        {drawer && (
          <motion.div
            className="fixed inset-0 z-30 bg-slate-950/40 backdrop-blur-sm md:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={() => setDrawer(false)}
            aria-hidden="true"
          />
        )}
      </AnimatePresence>

      {/* Logical borders and start/end offsets, so the rail sits on the correct edge
          in Arabic without a second layout. */}
      <nav
        id="nav-rail"
        aria-label={t('nav.label')}
        className={cn(
          'border-line bg-surface edge z-40 w-60 flex-col gap-8 px-5 py-6',
          // Mobile: an overlay drawer, toggled by presence rather than by a transform.
          // A translate needs ltr:/rtl: variants, and `[dir=ltr] &` outranks any
          // `md:` override on specificity — which is what hid the rail everywhere.
          'fixed top-0 bottom-0 start-0',
          drawer ? 'flex' : 'hidden',
          'md:bg-surface/75 md:sticky md:top-0 md:flex md:h-[100dvh] md:w-auto md:border-e md:backdrop-blur-xl',
        )}
      >
        <div className="flex items-center gap-3">
          <motion.img
            src="/az-bot.png"
            alt=""
            width={36}
            height={36}
            className="size-9 rounded-full ring-1 ring-black/5 dark:ring-white/10"
            whileHover={{ scale: 1.06, rotate: -3 }}
            transition={{ type: 'spring', stiffness: 100, damping: 20 }}
          />
          <div className="min-w-0 flex-1">
            <p className="text-ink text-sm font-semibold tracking-tight">{t('app.name')}</p>
            <p className="text-ink-faint truncate text-xs">{t('app.tagline')}</p>
          </div>
          <button
            type="button"
            onClick={() => setDrawer(false)}
            aria-label={t('nav.close')}
            className="text-ink-muted hover:text-ink -me-1 flex size-9 cursor-pointer items-center justify-center rounded-md transition-colors md:hidden"
          >
            <XIcon size={18} />
          </button>
        </div>

        {/* The palette is the fast path once the rail is memorised; the shortcut is
            printed on it so it can be discovered without documentation. */}
        <button
          type="button"
          onClick={() => setCmdOpen(true)}
          className="border-line text-ink-faint hover:text-ink hidden cursor-pointer items-center gap-2 rounded-md border px-2.5 py-2 text-sm transition-colors md:flex"
        >
          <MagnifyingGlassIcon size={15} className="shrink-0" />
          <span className="min-w-0 flex-1 truncate text-start">{t('cmd.open')}</span>
          <kbd className="border-line rounded border px-1 py-px text-[0.625rem] tracking-wide">
            ⌘K
          </kbd>
        </button>

        <div className="flex flex-1 flex-col gap-6 overflow-y-auto">
          {NAV.map(({ section, items }) => (
            <div key={section} className="flex flex-col gap-1">
              <p className="text-ink-faint px-2 pb-1 text-[0.6875rem] font-medium tracking-wide uppercase">
                {t(section)}
              </p>
              {items.map(({ route: r, labelKey, Icon }) => {
                const active = r === route
                return (
                  <button
                    key={r}
                    type="button"
                    onClick={() => go(r)}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'relative flex min-h-11 cursor-pointer items-center gap-3 rounded-md px-2 text-sm transition-colors md:min-h-0 md:py-2',
                      'hover:text-ink active:translate-y-px',
                      active ? 'text-ink font-medium' : 'text-ink-muted',
                    )}
                  >
                    {active && (
                      <motion.span
                        layoutId="nav-active"
                        className="bg-slate-100 dark:bg-slate-850 absolute inset-0 -z-10 rounded-md"
                        transition={{ type: 'spring', stiffness: 100, damping: 20 }}
                      />
                    )}
                    <Icon
                      size={17}
                      weight={active ? 'fill' : 'regular'}
                      className={active ? 'text-accent shrink-0' : 'shrink-0'}
                    />
                    {t(labelKey)}
                  </button>
                )
              })}
            </div>
          ))}
        </div>

        <div className="flex flex-col gap-3">
          <SystemStrip route={route} onNavigate={go} />
          <ServerStatus />

          <div className="flex items-center justify-between gap-2">
            <fieldset className="border-line m-0 flex rounded-md border p-0.5">
              <legend className="sr-only">{t('lang.label')}</legend>
              {LOCALES.map((l: Locale) => (
                <button
                  key={l}
                  type="button"
                  onClick={() => setLocale(l)}
                  aria-pressed={l === locale}
                  className={cn(
                    'cursor-pointer rounded px-2 py-1 text-xs transition-colors',
                    l === locale
                      ? 'bg-slate-100 text-ink dark:bg-slate-850'
                      : 'text-ink-faint hover:text-ink',
                  )}
                >
                  {LOCALE_LABEL[l]}
                </button>
              ))}
            </fieldset>

            <div className="flex items-center gap-2">
              {/* Opens upward: this bell sits at the bottom of a full-height rail. */}
              <Bell onNavigate={onNavigate} placement="up" />
              <SettingsPanel />
              <button
                type="button"
                onClick={toggle}
                title={theme === 'dark' ? t('theme.toLight') : t('theme.toDark')}
                aria-label={theme === 'dark' ? t('theme.toLight') : t('theme.toDark')}
                className="border-line text-ink-muted hover:text-ink cursor-pointer rounded-md border p-1.5 transition-colors active:translate-y-px"
              >
                {theme === 'dark' ? <SunIcon size={15} /> : <MoonIcon size={15} />}
              </button>
            </div>
          </div>

          <SignOut />
        </div>
      </nav>

      <main id="main" tabIndex={-1} className="min-w-0 px-4 py-8 md:px-10 md:py-12">
        <div className="mx-auto max-w-[1400px]">{children}</div>
      </main>

      <CommandPalette
        open={cmdOpen}
        onClose={() => setCmdOpen(false)}
        onNavigate={onNavigate}
        route={route}
      />
    </div>
  )
}

/**
 * Logs and the retry queue, as two instrument pills above the server status.
 *
 * They were the last two rows of an "Administration" list, which put "read the
 * pipeline's stack traces" at the same weight as "write today's report". Here
 * they read as what they are — a gauge each, with the number that decides
 * whether they are worth opening: errors in the last 24 h, and writes Google
 * has not accepted yet. A zero stays quiet; anything else colours itself.
 *
 * Both counts come from the `logs` key `OpsProvider` already polls, so the
 * strip costs no extra request.
 */
function SystemStrip({
  route,
  onNavigate,
}: {
  readonly route: Route
  readonly onNavigate: (r: Route) => void
}) {
  const { t } = useI18n()
  const { stats } = useOps()

  const gauges = [
    {
      item: SYSTEM_NAV[0],
      count: stats?.last_24h.error ?? 0,
      tone: 'text-status-fail',
    },
    {
      item: SYSTEM_NAV[1],
      count: stats?.pending_sheet_writes ?? 0,
      tone: 'text-status-warn',
    },
  ]

  return (
    // Stacked, not side by side: two pills sharing a 240px rail left ~45px for
    // the label, so both read "Journ…" and "File d'att…" — a gauge nobody can
    // name is not a gauge. Full width costs one more row and keeps the words.
    <div className="flex flex-col gap-1.5">
      {gauges.map(({ item, count, tone }) => {
        const active = item.route === route
        const { Icon } = item
        return (
          <button
            key={item.route}
            type="button"
            onClick={() => onNavigate(item.route)}
            aria-current={active ? 'page' : undefined}
            title={t(item.labelKey)}
            className={cn(
              'border-line focus-visible:ring-accent flex w-full min-w-0 cursor-pointer items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs transition-colors outline-none active:translate-y-px focus-visible:ring-2',
              active
                ? 'bg-slate-100 text-ink dark:bg-slate-850'
                : 'text-ink-faint hover:text-ink',
            )}
          >
            <Icon size={14} weight={active ? 'fill' : 'regular'} className="shrink-0" />
            <span className="min-w-0 flex-1 truncate text-start">{t(item.labelKey)}</span>
            {count > 0 && (
              <span className={cn('tabular shrink-0 font-semibold', tone)}>
                {count > 99 ? '99+' : count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/** Who is signed in, and the way out — two separate rows, since a name and an
 *  action read as one confusing control when squeezed onto a single button. */
function SignOut() {
  const { t } = useI18n()
  const { user, signOut } = useAuth()
  if (!user) return null
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 px-1">
        <span className="bg-slate-100 text-ink-muted dark:bg-slate-850 flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-medium">
          {user.name.slice(0, 1).toUpperCase()}
        </span>
        <span className="text-ink min-w-0 flex-1 truncate text-sm font-medium">{user.name}</span>
      </div>

      <button
        type="button"
        onClick={() => void signOut()}
        aria-label={t('auth.signOut')}
        className="border-line text-ink-muted hover:text-ink focus-visible:ring-accent flex min-h-11 w-full cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors outline-none active:translate-y-px focus-visible:ring-2"
      >
        <SignOutIcon size={16} className="shrink-0" />
        <span>{t('auth.signOut')}</span>
      </button>
    </div>
  )
}
