import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

export const REFRESH_CHOICES = [15_000, 30_000, 60_000, 0] as const
export type Density = 'comfortable' | 'compact'

export interface Settings {
  /** Poll interval in ms. 0 means manual refresh only. */
  refreshMs: number
  /** Extractions at or below this confidence are shown as weak. */
  confidence: number
  density: Density
}

const DEFAULTS: Settings = { refreshMs: 60_000, confidence: 0.7, density: 'comfortable' }
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

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(initial)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
    document.documentElement.dataset.density = settings.density
  }, [settings])

  const update = useCallback(
    (patch: Partial<Settings>) => setSettings((s) => ({ ...s, ...patch })),
    [],
  )
  const reset = useCallback(() => setSettings(DEFAULTS), [])

  const value = useMemo(() => ({ settings, update, reset }), [settings, update, reset])
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}

export function useSettings() {
  const ctx = useContext(SettingsContext)
  if (!ctx) throw new Error('useSettings must be used inside SettingsProvider')
  return ctx
}
