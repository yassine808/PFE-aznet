import { motion } from 'motion/react'
import { AppShell } from '@/components/app-shell'
import { OverviewPage } from '@/pages/overview'
import { ReportsPage } from '@/pages/reports'
import { InboxPage } from '@/pages/inbox'
import { DailyReportPage } from '@/pages/daily-report'
import { WeeklyReportPage } from '@/pages/weekly-report'
import { useI18n } from '@/lib/i18n'
import { useRoute, type Route } from '@/lib/router'

const TITLE_KEY: Record<Route, string> = {
  overview: 'page.overview.title',
  inbox: 'page.inbox.title',
  reports: 'page.reports.title',
  daily: 'page.daily.title',
  weekly: 'page.weekly.title',
  pipeline: 'page.pipeline.title',
  queue: 'page.queue.title',
}

const PAGES: Partial<Record<Route, () => React.ReactElement>> = {
  overview: OverviewPage,
  inbox: InboxPage,
  reports: ReportsPage,
  daily: DailyReportPage,
  weekly: WeeklyReportPage,
}

export default function App() {
  const [route, navigate] = useRoute()
  const { t } = useI18n()
  const Page = PAGES[route]

  return (
    <AppShell route={route} onNavigate={navigate}>
      {/* Keyed on route so each navigation replays the entrance. */}
      <motion.div
        key={route}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 100, damping: 20 }}
      >
        {/* Overview has no h1: the masthead is the page header, and two would compete. */}
        {route !== 'overview' && (
          <header className="border-line border-b pb-6">
            <h1 className="text-ink text-3xl font-semibold tracking-tighter">{t(TITLE_KEY[route])}</h1>
          </header>
        )}

        {Page ? (
          <Page />
        ) : (
          <section className="py-16">
            <p className="text-ink-faint max-w-[65ch] text-sm">{t('state.empty.body')}</p>
          </section>
        )}
      </motion.div>
    </AppShell>
  )
}
