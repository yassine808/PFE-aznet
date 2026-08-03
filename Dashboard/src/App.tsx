import { Suspense, lazy, useEffect } from 'react'
import { motion } from 'motion/react'
import { AppShell } from '@/components/app-shell'
import { OverviewPage } from '@/pages/overview'
import { AuthProvider, useAuth, usePageTimer } from '@/lib/auth'
import { SettingsProvider } from '@/lib/settings'
import { OpsProvider } from '@/lib/ops-context'
import { useI18n } from '@/lib/i18n'
import { useRoute, type Route } from '@/lib/router'

// Pages arrive as separate chunks, fetched on first visit: the initial bundle
// stays small (Overview — the default route — is the only eager one) and the
// rest of the dashboard costs nothing until it is opened. The blank-canvas
// fallback mirrors the auth-loading blank, so navigation never flashes chrome.
const InboxPage = lazy(() => import('@/pages/inbox').then((m) => ({ default: m.InboxPage })))
const ReportsPage = lazy(() => import('@/pages/reports').then((m) => ({ default: m.ReportsPage })))
const DailyReportPage = lazy(() => import('@/pages/daily-report').then((m) => ({ default: m.DailyReportPage })))
const WeeklyReportPage = lazy(() => import('@/pages/weekly-report').then((m) => ({ default: m.WeeklyReportPage })))
const EquipePage = lazy(() => import('@/pages/equipe').then((m) => ({ default: m.EquipePage })))
const AutomationPage = lazy(() => import('@/pages/automation').then((m) => ({ default: m.AutomationPage })))
const TasksPage = lazy(() => import('@/pages/tasks').then((m) => ({ default: m.TasksPage })))
const LogsPage = lazy(() => import('@/pages/logs').then((m) => ({ default: m.LogsPage })))
const QueuePage = lazy(() => import('@/pages/queue').then((m) => ({ default: m.QueuePage })))
const LoginPage = lazy(() => import('@/pages/login').then((m) => ({ default: m.LoginPage })))

const TITLE_KEY: Record<Route, string> = {
  overview: 'page.overview.title',
  inbox: 'page.inbox.title',
  reports: 'page.reports.title',
  daily: 'page.daily.title',
  weekly: 'page.weekly.title',
  automation: 'page.automation.title',
  tasks: 'page.tasks.title',
  logs: 'page.logs.title',
  queue: 'page.queue.title',
  equipe: 'page.equipe.title',
}

export default function App() {
  return (
    <AuthProvider>
      {/* Inside AuthProvider on purpose: the settings live in the database now,
          so the provider needs to know whose preferences to load. */}
      <SettingsProvider>
        <Gate />
      </SettingsProvider>
    </AuthProvider>
  )
}

/**
 * Login screen or app.
 *
 * Not a security boundary — every endpoint is gated on the API, so bypassing
 * this in devtools gains nothing. It exists so the dashboard knows whose name
 * to put on an action.
 */
function Gate() {
  const { user, loading } = useAuth()
  const { t } = useI18n()
  // Blank rather than the login screen while /auth/me is in flight: flashing
  // "sign in" on every refresh reads as having been logged out.
  if (loading) return <main className="bg-canvas min-h-screen" />
  if (!user) {
    document.title = `${t('page.login.title')} �?" ${t('app.name')}`
    return (
      <Suspense fallback={<main className="bg-canvas min-h-screen" />}>
        <LoginPage />
      </Suspense>
    )
  }
  return <Dashboard />
}

/** Renders the page for the current route. A switch, not a ternary chain, so
 *  adding a route is one case rather than one more branch to thread through. */
function RouteView({
  route,
  params,
  navigate,
}: {
  readonly route: Route
  readonly params: Record<string, string>
  readonly navigate: ReturnType<typeof useRoute>[1]
}) {
  const { t } = useI18n()
  switch (route) {
    case 'overview':
      return <OverviewPage onOpenDay={(iso) => navigate('inbox', { date: iso })} />
    case 'inbox':
      return <InboxPage initialDate={params.date} />
    case 'reports':
      return <ReportsPage />
    case 'daily':
      return <DailyReportPage />
    case 'weekly':
      return <WeeklyReportPage />
    case 'automation':
      return <AutomationPage />
    case 'tasks':
      return <TasksPage />
    case 'logs':
      return <LogsPage />
    case 'queue':
      return <QueuePage />
    case 'equipe':
      return <EquipePage />
    default:
      return (
        <section className="py-16">
          <p className="text-ink-faint max-w-[65ch] text-sm">{t('state.empty.body')}</p>
        </section>
      )
  }
}

function Dashboard() {
  const [loc, navigate] = useRoute()
  const { t } = useI18n()
  const { route, params } = loc

  // Above the router, so a page cannot unmount before reporting its own time.
  usePageTimer(route, true)

  // The tab title follows the route so several open tabs are tellable apart;
  // the in-page h1 below is the visible twin of this.
  useEffect(() => {
    document.title = `${t(TITLE_KEY[route])} — ${t('app.name')}`
  }, [route, t])

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
              <h1 className="text-ink text-3xl font-semibold tracking-tighter">
                {t(TITLE_KEY[route])}
              </h1>
            </header>
          )}

          {/* Suspense here, not inside RouteView: the shell, title and
              entrance animation paint while a lazily-loaded page chunk
              streams in; only the content area waits. */}
          <Suspense fallback={<div className="min-h-[70vh]" />}>
            <RouteView route={route} params={params} navigate={navigate} />
          </Suspense>
        </motion.div>
      </AppShell>
    </OpsProvider>
  )
}

