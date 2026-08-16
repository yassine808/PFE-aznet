import {
  BuildingsIcon,
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
 *
 * Grouped by **whose data a page shows**, not by what it is made of:
 *
 * - *Aperçu* — the one page that answers "what is happening", for everyone.
 * - *Mon périmètre* — pages whose content changes with who is signed in. A chef
 *   opening Réception sees their own crew's messages and their own team's
 *   digest; the director sees the company. Same route, different reading.
 * - *Commun* — the org chart, the scheduler and the shared to-do list are the
 *   same for every account, which is exactly why they belong apart from the
 *   ones above.
 *
 * The grouping labels the scope; it does not gate it. Every account still
 * reaches every page, and the API is where access is actually decided —
 * hiding a button has never stopped anyone who can type a URL.
 */
export const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: 'nav.section.overview',
    items: [
      {
        route: 'overview',
        labelKey: 'nav.overview',
        keywordsKey: 'nav.kw.overview',
        Icon: ChartBarIcon,
      },
    ],
  },
  {
    section: 'nav.section.scope',
    items: [
      { route: 'inbox', labelKey: 'nav.inbox', keywordsKey: 'nav.kw.inbox', Icon: TrayIcon },
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
    section: 'nav.section.shared',
    items: [
      // One entry where there were two: accounts and bot authorisation are the
      // same people since `users` folded into `persons`.
      {
        route: 'equipe',
        labelKey: 'nav.equipe',
        keywordsKey: 'nav.kw.equipe',
        Icon: UsersThreeIcon,
      },
      {
        // A site is a real entity — a journal tab, a bordereau, a crew — and
        // until 2026-08-16 it had no page: confirming one was a banner on
        // Overview, which answers "what is happening today", not "look after
        // the sites".
        route: 'chantiers',
        labelKey: 'nav.chantiers',
        keywordsKey: 'nav.kw.chantiers',
        Icon: BuildingsIcon,
      },
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
    ],
  },
]

/**
 * The machine's own two pages. Out of the rail's list and into a strip beside
 * the server status, because that is what they are: instrumentation, checked
 * when something looks wrong, not places anyone works. They keep their entries
 * in `NAV_ITEMS` so the command palette still finds them by name.
 */
export const SYSTEM_NAV: NavItem[] = [
  { route: 'logs', labelKey: 'nav.logs', keywordsKey: 'nav.kw.logs', Icon: PulseIcon },
  { route: 'queue', labelKey: 'nav.queue', keywordsKey: 'nav.kw.queue', Icon: StackIcon },
]

export const NAV_ITEMS: NavItem[] = [...NAV.flatMap((s) => s.items), ...SYSTEM_NAV]

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
