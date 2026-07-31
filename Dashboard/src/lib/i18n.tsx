import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import ar from '@/locales/ar.json'
import en from '@/locales/en.json'
import fr from '@/locales/fr.json'

export const LOCALES = ['fr', 'en', 'ar'] as const
export type Locale = (typeof LOCALES)[number]

export const LOCALE_LABEL: Record<Locale, string> = { fr: 'FR', en: 'EN', ar: 'ع' }

const INTL_LOCALE: Record<Locale, string> = { fr: 'fr-FR', en: 'en-GB', ar: 'ar-MA' }

/** Maps our three-locale app setting onto the BCP-47 tag Intl.* formatters expect. */
export function intlLocaleOf(locale: Locale): string {
  return INTL_LOCALE[locale]
}

// fr is the reference: every key exists here, and it is what a missing translation falls back to.
const DICTIONARIES: Record<Locale, Record<string, string>> = { fr, en, ar }

const STORAGE_KEY = 'aznet.locale'

const I18nContext = createContext<{
  locale: Locale
  setLocale: (l: Locale) => void
  dir: 'ltr' | 'rtl'
  t: (key: string, vars?: Record<string, string | number>) => string
} | null>(null)

function initialLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY)
  return LOCALES.includes(stored as Locale) ? (stored as Locale) : 'fr'
}

export function I18nProvider({ children }: { readonly children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(initialLocale)
  const dir: 'ltr' | 'rtl' = locale === 'ar' ? 'rtl' : 'ltr'

  useEffect(() => {
    document.documentElement.lang = locale
    document.documentElement.dir = dir
    localStorage.setItem(STORAGE_KEY, locale)
  }, [locale, dir])

  // A missing key surfaces as the key itself. Silent fallback to a blank string hides gaps.
  // `{name}` placeholders are filled from `vars`; an unmatched one is left visible
  // for the same reason — a sentence reading "{count} rapports" is a bug report.
  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const text = DICTIONARIES[locale][key] ?? fr[key as keyof typeof fr] ?? key
      if (!vars) return text
      return text.replace(/\{(\w+)\}/g, (match, name) =>
        name in vars ? String(vars[name]) : match,
      )
    },
    [locale],
  )

  const value = useMemo(() => ({ locale, setLocale, dir, t }), [locale, setLocale, dir, t])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used inside I18nProvider')
  return ctx
}
