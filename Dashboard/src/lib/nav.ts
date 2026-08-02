import {
  CalendarBlankIcon,
  ChartBarIcon,
  CheckSquareIcon,
  ClockIcon,
  RowsIcon,
  PulseIcon,
  StackIcon,
  SunHorizonIcon,
  TrayIcon,
  UsersThreeIcon,
} from '@phosphor-icons/react'
import type { Route } from '@/lib/router'

export interface NavItem {
  route: Route
  labelKey: string
  /** Extra words the command palette matches on, so "email" finds the daily report. */
  keywordsKey: string
  Icon: typeof ChartBarIcon
}

/**
 * The single nav registry. The rail and the command palette both read it, so a
 * new page cannot appear in one and be missing from the other.
 */
export const NAV: { section: string; items: NavItem[] }[] = [
  {
    // The day-to-day working view: what came in, one message at a time.
    section: 'nav.section.overview',
    items: [
      {
        route: 'overview',
        labelKey: 'nav.overview',
        keywordsKey: 'nav.kw.overview',
        Icon: ChartBarIcon,
      },
      { route: 'inbox', labelKey: 'nav.inbox', keywordsKey: 'nav.kw.inbox', Icon: TrayIcon },
    ],
  },
  {
    // Everything that reads as "a report": the raw table and the two generated
    // digests. Grouped together so "Reports" names one thing, not two — it used
    // to also be the name of the section one level up from the Reports page.
    section: 'nav.section.reports',
    items: [
      { route: 'reports', labelKey: 'nav.reports', keywordsKey: 'nav.kw.reports', Icon: RowsIcon },
      { route: 'daily', labelKey: 'nav.daily', keywordsKey: 'nav.kw.daily', Icon: SunHorizonIcon },
      {
        route: 'weekly',
        labelKey: 'nav.weekly',
        keywordsKey: 'nav.kw.weekly',
        Icon: CalendarBlankIcon,
      },
    ],
  },
  {
    section: 'nav.section.admin',
    items: [
      {
        route: 'automation',
        labelKey: 'nav.automation',
        keywordsKey: 'nav.kw.automation',
        Icon: ClockIcon,
      },
      {
        route: 'tasks',
        labelKey: 'nav.tasks',
        keywordsKey: 'nav.kw.tasks',
        Icon: CheckSquareIcon,
      },
      // One entry where there were two: accounts and bot authorisation are the
      // same people since `users` folded into `persons`.
      {
        route: 'equipe',
        labelKey: 'nav.equipe',
        keywordsKey: 'nav.kw.equipe',
        Icon: UsersThreeIcon,
      },
      { route: 'logs', labelKey: 'nav.logs', keywordsKey: 'nav.kw.logs', Icon: PulseIcon },
      { route: 'queue', labelKey: 'nav.queue', keywordsKey: 'nav.kw.queue', Icon: StackIcon },
    ],
  },
]

export const NAV_ITEMS: NavItem[] = NAV.flatMap((s) => s.items)

export function navItem(route: Route): NavItem | undefined {
  return NAV_ITEMS.find((i) => i.route === route)
}

/** Strips accents so "resume" matches "résumé" and Arabic diacritics are ignored. */
export function fold(s: string): string {
  return s
    .toLowerCase()
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
}
