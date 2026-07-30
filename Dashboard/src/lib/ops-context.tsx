import { createContext, useContext, useEffect, useMemo, useRef, type ReactNode } from 'react'
import {
  api,
  pickReceptionWorkflow,
  postSamples,
  useApi,
  type Health,
  type LogEntry,
  type LogStats,
} from '@/lib/api'
import { buildServices, type ServiceRow } from '@/lib/services'
import { useI18n } from '@/lib/i18n'
import { useSettings } from '@/lib/settings'

interface Ops {
  services: ServiceRow[]
  health: Health | null
  healthError: string | null
  logs: LogEntry[]
  stats: LogStats | null
}

const OpsContext = createContext<Ops | null>(null)

const SAMPLE_MS = 60_000

/**
 * Owns operational polling and the uptime sampler for the whole app.
 *
 * Lives above the router on purpose: when the sampler lived inside the Overview
 * page it stopped the moment the user navigated elsewhere, so history had holes
 * that looked like downtime. Here it runs for as long as the app is open, and
 * every sample is written to Postgres so the record outlives the browser tab.
 */
export function OpsProvider({ children }: { children: ReactNode }) {
  const { locale } = useI18n()
  const { settings } = useSettings()
  const poll = settings.refreshMs || undefined

  const health = useApi('health', api.health, poll)
  const logs = useApi('logs', api.logs, poll)
  const n8n = useApi('n8n', api.n8n, poll)
  const executions = useApi('n8n-executions', api.n8nExecutions, poll)
  const reports = useApi('reports', api.reports, poll)

  const services = useMemo(
    () =>
      buildServices({
        health: health.data,
        healthError: health.error,
        logs: logs.data?.logs ?? [],
        stats: logs.data?.stats ?? null,
        logsError: logs.error,
        reportsOk: !reports.error,
        n8nReachable: n8n.data?.reachable ?? false,
        workflow: n8n.data ? pickReceptionWorkflow(n8n.data.workflows) : undefined,
        lastExecution: executions.data?.[0] ?? null,
        locale,
      }),
    [
      health.data,
      health.error,
      logs.data,
      logs.error,
      reports.error,
      n8n.data,
      executions.data,
      locale,
    ],
  )

  const servicesRef = useRef(services)
  servicesRef.current = services

  useEffect(() => {
    const send = () => {
      const rows = servicesRef.current
      // Nothing has resolved yet: writing "idle" for every service would record
      // a gap as a real observation.
      if (rows.length === 0) return
      void postSamples(rows.map((r) => ({ service: r.key, state: r.state })))
    }
    const first = window.setTimeout(send, 3_000)
    const timer = window.setInterval(send, SAMPLE_MS)
    return () => {
      window.clearTimeout(first)
      window.clearInterval(timer)
    }
  }, [])

  const value = useMemo<Ops>(
    () => ({
      services,
      health: health.data,
      healthError: health.error,
      logs: logs.data?.logs ?? [],
      stats: logs.data?.stats ?? null,
    }),
    [services, health.data, health.error, logs.data],
  )

  return <OpsContext.Provider value={value}>{children}</OpsContext.Provider>
}

export function useOps() {
  const ctx = useContext(OpsContext)
  if (!ctx) throw new Error('useOps must be used inside OpsProvider')
  return ctx
}
