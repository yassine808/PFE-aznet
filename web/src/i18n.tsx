import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

// All user-facing copy lives here — nothing is hardcoded in components.
// Keys are shared between locales; add a key to BOTH dictionaries.
export type Lang = "fr" | "en";

const DICT: Record<Lang, Record<string, string>> = {
  fr: {
    "brand.subtitle": "Rapports terrain",
    "nav.supervision": "Supervision",
    "nav.dashboard": "Tableau de bord",
    "nav.review": "À vérifier",
    "nav.reference": "Référentiel",
    "nav.technicians": "Techniciens",
    "nav.chantiers": "Chantiers",
    "nav.channels": "Canaux",
    "nav.admin": "Administration",
    "nav.settings": "Paramètres",
    "sidebar.status": "Réception Telegram + WhatsApp",
    "topbar.title": "Tableau de bord",
    "topbar.search": "Rechercher…",
    "topbar.refresh": "Rafraîchir",
    "topbar.lang": "Langue",
    "topbar.theme.toDark": "Passer en mode sombre",
    "topbar.theme.toLight": "Passer en mode clair",
    "kpi.total": "Rapports totaux",
    "kpi.total.hint": "{n} jour(s) couverts",
    "kpi.today": "Aujourd'hui",
    "kpi.review": "À vérifier",
    "kpi.review.hint": "{n}% du total",
    "kpi.techs": "Techniciens actifs",
    "kpi.techs.hint": "{n} chantier(s)",
    "chart.perDay.title": "Rapports par jour",
    "chart.perDay.subtitle": "7 derniers jours enregistrés",
    "chart.channel.title": "Rapports par canal",
    "chart.channel.subtitle": "Volume quotidien par canal, 7 derniers jours",
    "legend.whatsapp": "WhatsApp",
    "legend.telegram": "Telegram",
    "table.title": "Rapports journaliers",
    "filter.allTechs": "Tous les techniciens",
    "filter.allChantiers": "Tous les chantiers",
    "filter.review": "À vérifier",
    "table.rows": "{n} ligne(s)",
    "th.date": "Date",
    "th.channel": "Canal",
    "th.technician": "Technicien",
    "th.chantier": "Chantier",
    "th.activity": "Activité",
    "th.goulottes": "Goul. m",
    "th.cables": "Câbles m",
    "th.bureaux": "Bur.",
    "th.panneaux": "Pann.",
    "th.resume": "Résumé",
    "th.confidence": "Conf.",
    "state.loading": "Chargement…",
    "state.empty": "Aucun rapport ne correspond aux filtres.",
    "badge.review": "vérifier",
    "detail.transcription": "Transcription complète :",
    "detail.otherWork": "Autres travaux :",
    "detail.observations": "Observations :",
    "detail.audio": "Audio :",
    "detail.audioNote": "(lien durable : à venir — Drive upload)",
    "footer.editable": "Cliquer une cellule pour corriger — écrit directement dans Google Sheets. Colonnes éditables : {cols}.",
    "prompt.edit": "Corriger « {field} » (ligne {row})",
    "empty.dash": "—",
  },
  en: {
    "brand.subtitle": "Field reports",
    "nav.supervision": "Supervision",
    "nav.dashboard": "Dashboard",
    "nav.review": "To review",
    "nav.reference": "Directory",
    "nav.technicians": "Technicians",
    "nav.chantiers": "Sites",
    "nav.channels": "Channels",
    "nav.admin": "Administration",
    "nav.settings": "Settings",
    "sidebar.status": "Telegram + WhatsApp reception",
    "topbar.title": "Dashboard",
    "topbar.search": "Search…",
    "topbar.refresh": "Refresh",
    "topbar.lang": "Language",
    "topbar.theme.toDark": "Switch to dark mode",
    "topbar.theme.toLight": "Switch to light mode",
    "kpi.total": "Total reports",
    "kpi.total.hint": "{n} day(s) covered",
    "kpi.today": "Today",
    "kpi.review": "To review",
    "kpi.review.hint": "{n}% of total",
    "kpi.techs": "Active technicians",
    "kpi.techs.hint": "{n} site(s)",
    "chart.perDay.title": "Reports per day",
    "chart.perDay.subtitle": "Last 7 recorded days",
    "chart.channel.title": "Reports per channel",
    "chart.channel.subtitle": "Daily volume by channel, last 7 days",
    "legend.whatsapp": "WhatsApp",
    "legend.telegram": "Telegram",
    "table.title": "Daily reports",
    "filter.allTechs": "All technicians",
    "filter.allChantiers": "All sites",
    "filter.review": "To review",
    "table.rows": "{n} row(s)",
    "th.date": "Date",
    "th.channel": "Channel",
    "th.technician": "Technician",
    "th.chantier": "Site",
    "th.activity": "Activity",
    "th.goulottes": "Trunk. m",
    "th.cables": "Cables m",
    "th.bureaux": "Off.",
    "th.panneaux": "Pan.",
    "th.resume": "Summary",
    "th.confidence": "Conf.",
    "state.loading": "Loading…",
    "state.empty": "No report matches the filters.",
    "badge.review": "review",
    "detail.transcription": "Full transcription:",
    "detail.otherWork": "Other work:",
    "detail.observations": "Observations:",
    "detail.audio": "Audio:",
    "detail.audioNote": "(durable link: coming soon — Drive upload)",
    "footer.editable": "Click a cell to correct it — writes straight to Google Sheets. Editable columns: {cols}.",
    "prompt.edit": "Correct \"{field}\" (row {row})",
    "empty.dash": "—",
  },
};

type Vars = Record<string, string | number>;
type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (key: string, vars?: Vars) => string };

const I18nContext = createContext<Ctx | null>(null);
const STORAGE_KEY = "aznet.lang";

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === "en" || saved === "fr" ? saved : "fr";
  });

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    localStorage.setItem(STORAGE_KEY, l);
  }, []);

  useEffect(() => { document.documentElement.lang = lang; }, [lang]);

  const t = useCallback((key: string, vars?: Vars) => {
    let s = DICT[lang][key] ?? DICT.fr[key] ?? key;
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
    return s;
  }, [lang]);

  return <I18nContext.Provider value={{ lang, setLang, t }}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
