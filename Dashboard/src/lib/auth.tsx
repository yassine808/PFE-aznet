import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { login as apiLogin, logout as apiLogout, trackVisit, whoami, type Account } from '@/lib/api'

/**
 * Who is signed in, for the whole app.
 *
 * The session token is an httpOnly cookie — unreadable from JavaScript, so an
 * XSS cannot steal it. That also means the only way to know who we are is to
 * ask the server, which is what `whoami()` does on mount.
 *
 * `loading` matters: without it the app flashes the login screen on every
 * refresh while /auth/me is in flight, which reads as "you were logged out".
 */
interface AuthValue {
  user: Account | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { readonly children: ReactNode }) {
  const [user, setUser] = useState<Account | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const ac = new AbortController()
    whoami(ac.signal)
      .then((r) => setUser(r.user))
      .catch(() => setUser(null)) // API unreachable reads as signed out; the login screen says so
      .finally(() => setLoading(false))
    return () => ac.abort()
  }, [])

  // A 401 on *any* API call means the session is gone for good — the server
  // rejected it, so retrying cannot help. The event is dispatched by api.ts's
  // fail() (every authenticated request funnels through it); clearing the user
  // flips the Gate to the login screen and unmounts the polling panels.
  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener('aznet:unauthorized', onUnauthorized)
    return () => window.removeEventListener('aznet:unauthorized', onUnauthorized)
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    const r = await apiLogin(email, password)
    setUser(r.user)
  }, [])

  const signOut = useCallback(async () => {
    try {
      await apiLogout()
    } finally {
      // Cleared even if the request failed: the user asked to leave, and a
      // dashboard still showing their name after "log out" is worse than a
      // session row that expires on its own in seven days.
      setUser(null)
    }
  }, [])

  const value = useMemo(() => ({ user, loading, signIn, signOut }), [user, loading, signIn, signOut])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

/**
 * Records how long each page stayed open.
 *
 * The server cannot measure this — it only sees requests — so the timer lives
 * here and flushes on navigation and on tab close. Mounted once, above the
 * router: inside a page it would unmount before it could report.
 */
export function usePageTimer(route: string, enabled: boolean) {
  const since = useRef(Date.now())
  const current = useRef(route)

  useEffect(() => {
    if (!enabled) return
    const flush = () => {
      const seconds = Math.round((Date.now() - since.current) / 1000)
      if (seconds > 0) trackVisit(current.current, seconds)
      since.current = Date.now()
    }
    if (current.current !== route) {
      flush()
      current.current = route
    }
    // `pagehide` rather than `unload`: the latter is ignored by mobile Safari
    // and blocks the back/forward cache everywhere else.
    window.addEventListener('pagehide', flush)
    return () => {
      window.removeEventListener('pagehide', flush)
      // Logout unmounts Dashboard without a pagehide, so the last page's time
      // would be silently dropped; the route-change path flushes in the body
      // (a ~0 s second flush here is harmless).
      flush()
    }
  }, [route, enabled])
}
