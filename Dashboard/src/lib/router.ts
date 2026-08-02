import { useEffect, useState } from 'react'

export const ROUTES = [
  'overview',
  'inbox',
  'reports',
  'daily',
  'weekly',
  'automation',
  'tasks',
  'logs',
  'queue',
  'equipe',
] as const
export type Route = (typeof ROUTES)[number]

/**
 * `team` (accounts) and `access` (bot authorisation) merged into `equipe` when
 * `users` folded into `persons`. Kept as aliases rather than dropped: both were
 * live hash links in bookmarks and the command palette, and a stale one would
 * otherwise land silently on Overview with no hint of where the page went.
 */
const ALIASES: Record<string, Route> = { team: 'equipe', access: 'equipe' }

export interface Location {
  route: Route
  /** Query params after the route, e.g. #/inbox?date=2026-07-25 */
  params: Record<string, string>
}

function read(): Location {
  const raw = window.location.hash.replace(/^#\/?/, '')
  const [path, query = ''] = raw.split('?')
  const route = (ROUTES as readonly string[]).includes(path)
    ? (path as Route)
    : (ALIASES[path] ?? 'overview')
  const params: Record<string, string> = {}
  for (const [k, v] of new URLSearchParams(query)) params[k] = v
  return { route, params }
}

/**
 * ponytail: hash routing on the native hashchange event, no router dependency.
 * Flat routes with an optional query string, which is all the cross-panel links
 * need (Overview's year graph deep-links into Inbox for one day).
 */
export function useRoute(): [Location, (route: Route, params?: Record<string, string>) => void] {
  const [loc, setLoc] = useState<Location>(read)

  useEffect(() => {
    const onChange = () => setLoc(read())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const navigate = (route: Route, params?: Record<string, string>) => {
    const query = params && Object.keys(params).length ? `?${new URLSearchParams(params)}` : ''
    window.location.hash = `/${route}${query}`
  }

  return [loc, navigate]
}
