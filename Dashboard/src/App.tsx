import { motion } from 'motion/react'
import { AppShell } from '@/components/app-shell'
import { OverviewPage } from '@/pages/overview'
import { ReportsPage } from '@/pages/reports'
import { InboxPage } from '@/pages/inbox'
import { DailyReportPage } from '@/pages/daily-report'
import { WeeklyReportPage } from '@/pages/weekly-report'
import { AccessControlPage } from '@/pages/access-control'
import { AutomationPage } from '@/pages/automation'
import { LogsPage } from '@/pages/logs'
import { OpsProvider } from '@/lib/ops-context'
import { useI18n } from '@/lib/i18n'
import { useRoute, type Route } from '@/lib/router'

const TITLE_KEY: Record<Route, string> = {
  overview: 'page.overview.title',
  inbox: 'page.inbox.title',
  reports: 'page.reports.title',
  daily: 'page.daily.title',
  weekly: 'page.weekly.title',
  automation: 'page.automation.title',
  access: 'page.access.title',
  logs: 'page.logs.title',
  queue: 'page.queue.title',
}

export default function App() {
  const [loc, navigate] = useRoute()
  const { t } = useI18n()
  const { route, params } = loc

  return (
    // Above the router: the uptime sampler must keep writing regardless of
    // which panel is open.
    <OpsProvider>
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

          {route === 'overview' ? (
            <OverviewPage onOpenDay={(iso) => navigate('inbox', { date: iso })} />
          ) : route === 'inbox' ? (
            <InboxPage initialDate={params.date} />
          ) : route === 'reports' ? (
            <ReportsPage />
          ) : route === 'daily' ? (
            <DailyReportPage />
          ) : route === 'weekly' ? (
            <WeeklyReportPage />
          ) : route === 'automation' ? (
            <AutomationPage />
          ) : route === 'access' ? (
            <AccessControlPage />
          ) : route === 'logs' ? (
            <LogsPage />
          ) : (
            <section className="py-16">
              <p className="text-ink-faint max-w-[65ch] text-sm">{t('state.empty.body')}</p>
            </section>
          )}
        </motion.div>
      </AppShell>
    </OpsProvider>
  )
}
