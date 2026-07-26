import { motion } from 'motion/react'
import { AppShell } from '@/components/app-shell'
import { OverviewPage } from '@/pages/overview'
import { useI18n } from '@/lib/i18n'
import { useRoute, type Route } from '@/lib/router'

const TITLE_KEY: Record<Route, string> = {
  overview: 'page.overview.title',
  pipeline: 'page.pipeline.title',
  reports: 'page.reports.title',
  queue: 'page.queue.title',
}

export default function App() {
  const [route, navigate] = useRoute()
  const { t } = useI18n()

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

        {route === 'overview' ? (
          <OverviewPage />
        ) : (
          <section className="py-16">
            <p className="text-ink-faint max-w-[65ch] text-sm">{t('state.empty.body')}</p>
          </section>
        )}
      </motion.div>
    </AppShell>
  )
}
