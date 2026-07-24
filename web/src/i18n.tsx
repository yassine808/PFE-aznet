import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import fr from "./locales/fr.json";
import en from "./locales/en.json";
import ar from "./locales/ar.json";

// Copy lives in src/locales/{fr,en,ar}.json — nothing hardcoded in components.
// Add a key to every locale file (fr is the reference/fallback).
export type Lang = "fr" | "en" | "ar";

const DICT: Record<Lang, Record<string, string>> = { fr, en, ar };
const RTL: Lang[] = ["ar"];
export const LANGS: Lang[] = ["fr", "en", "ar"];

type Vars = Record<string, string | number>;
type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (key: string, vars?: Vars) => string; rtl: boolean };

const I18nContext = createContext<Ctx | null>(null);
const STORAGE_KEY = "aznet.lang";

function isLang(v: string | null): v is Lang {
  return v === "fr" || v === "en" || v === "ar";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return isLang(saved) ? saved : "fr";
  });

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    localStorage.setItem(STORAGE_KEY, l);
  }, []);

  // Drive <html lang> and text direction (RTL for Arabic).
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = RTL.includes(lang) ? "rtl" : "ltr";
  }, [lang]);

  const t = useCallback((key: string, vars?: Vars) => {
    let s = DICT[lang][key] ?? DICT.fr[key] ?? key;
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
    return s;
  }, [lang]);

  return (
    <I18nContext.Provider value={{ lang, setLang, t, rtl: RTL.includes(lang) }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
