import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { meSettings, putMeSettings } from '@/lib/api'
import { useAuth } from '@/lib/auth'

export const REFRESH_CHOICES = [15_000, 30_000, 60_000, 0] as const
export type Density = 'comfortable' | 'compact'
export type TimeFormat = '24h' | '12h'

export interface Settings {
  /** Poll interval in ms. 0 means manual refresh only. */
  refreshMs: number
  /** Extractions at or below this confidence are shown as weak. */
  confidence: number
  density: Density
  /** Clock display: 24h is the local (Morocco) convention, 12h is a choice. */
  timeFormat: TimeFormat
}

const DEFAULTS: Settings = {
  refreshMs: 60_000,
  confidence: 0.7,
  density: 'comfortable',
  timeFormat: '24h',
}
const STORAGE_KEY = 'aznet.settings'

const SettingsContext = createContext<{
  settings: Settings
  update: (patch: Partial<Settings>) => void
  reset: () => void
} | null>(null)

function initial(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULTS
    const parsed = JSON.parse(raw) as Partial<Settings>
    // Merge over defaults: a settings file from an older version must not
    // leave a key undefined and crash a consumer.
    return { ...DEFAULTS, ...parsed }
  } catch {
    return DEFAULTS
  }
}

export function SettingsProvider({ children }: { readonly children: ReactNode }) {
  const { user } = useAuth()
  const userId = user?.id
  const [settings, setSettings] = useState<Settings>(initial)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
    document.documentElement.dataset.density = settings.density
  }, [settings])

  // The database is authoritative per account: on login (and account change)
  // pull what this person chose and let it override whatever this browser had
  // cached — localStorage is a shared cache, two accounts on one browser must
  // not leak preferences into each other. Signed out, the browser copy holds.
  useEffect(() => {
    if (!userId) return
    let cancelled = false
    meSettings()
      .then((r) => {
        if (cancelled) return
        // The server blob only ever held what the client PUT, so trusting its
        // shape here is safe; the cast is for the loose `MeSettings` contract.
        setSettings((prev) => ({ ...DEFAULTS, ...prev, ...(r.settings as Partial<Settings>) }))
      })
      .catch((err) => console.error('[settings] sync failed:', err))
    return () => {
      cancelled = true
    }
  }, [userId])

  const update = useCallback(
    (patch: Partial<Settings>) => {
      setSettings((s) => ({ ...s, ...patch }))
      // Fire-and-forget with a visible trace: a dropped save is a preference
      // that reverts at next login, so it must be loud in devtools, not silent.
      if (user) putMeSettings(patch).catch((err) => console.error('[settings] save failed:', err))
    },
    [user],
  )

  const reset = useCallback(() => {
    setSettings(DEFAULTS)
    if (user) {
      // Every key back to its default. Confidence stays out of a chef's PUT:
      // the API rejects it and their account never owned the value anyway.
      const defaults: Partial<Settings> =
        user.role === 'directeur'
          ? DEFAULTS
          : { refreshMs: DEFAULTS.refreshMs, density: DEFAULTS.density, timeFormat: DEFAULTS.timeFormat }
      putMeSettings(defaults).catch((err) => console.error('[settings] reset failed:', err))
    }
  }, [user])

  const value = useMemo(() => ({ settings, update, reset }), [settings, update, reset])
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}

export function useSettings() {
  const ctx = useContext(SettingsContext)
  if (!ctx) throw new Error('useSettings must be used inside SettingsProvider')
  return ctx
}
