import { useEffect, useState } from 'react'

export const ROUTES = ['overview', 'inbox', 'reports', 'daily', 'weekly', 'pipeline', 'queue'] as const
export type Route = (typeof ROUTES)[number]

function read(): Route {
  const hash = window.location.hash.replace(/^#\/?/, '')
  return (ROUTES as readonly string[]).includes(hash) ? (hash as Route) : 'overview'
}

/**
 * ponytail: hash routing on the native hashchange event, no router dependency.
 * Four flat routes, no nesting, no loaders, no code splitting needed.
 * Swap in react-router if nested routes or route-level data loading ever appear.
 */
export function useRoute(): [Route, (r: Route) => void] {
  const [route, setRoute] = useState<Route>(read)

  useEffect(() => {
    const onChange = () => setRoute(read())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  return [route, (r: Route) => { window.location.hash = `/${r}` }]
}
