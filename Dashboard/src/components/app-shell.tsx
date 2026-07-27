import type { ReactNode } from 'react'
import { motion } from 'motion/react'
import {
  CalendarBlankIcon,
  ChartBarIcon,
  MoonIcon,
  PathIcon,
  RowsIcon,
  StackIcon,
  SunHorizonIcon,
  SunIcon,
  TrayIcon,
  UsersThreeIcon,
} from '@phosphor-icons/react'
import { LOCALES, LOCALE_LABEL, useI18n, type Locale } from '@/lib/i18n'
import { useTheme } from '@/lib/theme'
import { ServerStatus } from '@/components/server-status'
import { SettingsPanel } from '@/components/settings-panel'
import { cn } from '@/lib/utils'
import type { Route } from '@/lib/router'

const NAV: { section: string; items: { route: Route; labelKey: string; Icon: typeof ChartBarIcon }[] }[] = [
  {
    section: 'nav.section.read',
    items: [
      { route: 'overview', labelKey: 'nav.overview', Icon: ChartBarIcon },
      { route: 'inbox', labelKey: 'nav.inbox', Icon: TrayIcon },
      { route: 'reports', labelKey: 'nav.reports', Icon: RowsIcon },
    ],
  },
  {
    section: 'nav.section.reports',
    items: [
      { route: 'daily', labelKey: 'nav.daily', Icon: SunHorizonIcon },
      { route: 'weekly', labelKey: 'nav.weekly', Icon: CalendarBlankIcon },
    ],
  },
  {
    section: 'nav.section.ops',
    items: [
      { route: 'access', labelKey: 'nav.access', Icon: UsersThreeIcon },
      { route: 'pipeline', labelKey: 'nav.pipeline', Icon: PathIcon },
      { route: 'queue', labelKey: 'nav.queue', Icon: StackIcon },
    ],
  },
]

export function AppShell({
  route,
  onNavigate,
  children,
}: {
  route: Route
  onNavigate: (r: Route) => void
  children: ReactNode
}) {
  const { t, locale, setLocale } = useI18n()
  const { theme, toggle } = useTheme()

  return (
    <div className="min-h-[100dvh] md:grid md:grid-cols-[15rem_1fr]">
      {/* Logical borders, so the rail sits on the correct edge in Arabic without a second layout. */}
      <nav className="border-line bg-surface/75 edge flex flex-col gap-8 border-b px-5 py-6 backdrop-blur-xl md:sticky md:top-0 md:h-[100dvh] md:border-b-0 md:border-e">
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
          <div className="min-w-0">
            <p className="text-ink text-sm font-semibold tracking-tight">{t('app.name')}</p>
            <p className="text-ink-faint truncate text-xs">{t('app.tagline')}</p>
          </div>
        </div>

        <div className="flex flex-1 flex-col gap-6">
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
                    onClick={() => onNavigate(r)}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'relative flex items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors',
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
                    <Icon size={17} weight={active ? 'fill' : 'regular'} className={active ? 'text-accent' : ''} />
                    {t(labelKey)}
                  </button>
                )
              })}
            </div>
          ))}
        </div>

        <div className="flex flex-col gap-3">
          <ServerStatus />

          <div className="flex items-center justify-between gap-2">
            <div className="border-line flex rounded-md border p-0.5" role="group" aria-label={t('lang.label')}>
              {LOCALES.map((l: Locale) => (
                <button
                  key={l}
                  type="button"
                  onClick={() => setLocale(l)}
                  aria-pressed={l === locale}
                  className={cn(
                    'rounded px-2 py-1 text-xs transition-colors',
                    l === locale ? 'bg-slate-100 text-ink dark:bg-slate-850' : 'text-ink-faint hover:text-ink',
                  )}
                >
                  {LOCALE_LABEL[l]}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <SettingsPanel />
              <button
                type="button"
                onClick={toggle}
                title={theme === 'dark' ? t('theme.toLight') : t('theme.toDark')}
                aria-label={theme === 'dark' ? t('theme.toLight') : t('theme.toDark')}
                className="border-line text-ink-muted hover:text-ink rounded-md border p-1.5 transition-colors active:translate-y-px"
              >
                {theme === 'dark' ? <SunIcon size={15} /> : <MoonIcon size={15} />}
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="min-w-0 px-4 py-8 md:px-10 md:py-12">
        <div className="mx-auto max-w-[1400px]">{children}</div>
      </main>
    </div>
  )
}
