import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export type Theme = "dark" | "light";

// Recharts renders SVG and can't read CSS variables, so chart colors are
// duplicated here per theme (the one place the palette isn't in index.css).
export interface ChartTheme {
  grid: string;
  axis: string;      // faint tick labels
  axisStrong: string;
  accent: string;    // bars
  accentTop: string; // bar gradient top
  wa: string;        // WhatsApp line
  tg: string;        // Telegram line
  tooltipBg: string;
  tooltipBorder: string;
  tooltipInk: string;
  glow: string;      // drop-shadow color for the step lines
}

// Neutral / monochrome to match the reference: grayscale bars, white glow line,
// channels distinguished by tone (white vs mid-gray) rather than hue.
export const CHART: Record<Theme, ChartTheme> = {
  dark: {
    grid: "#222222", axis: "#737373", axisStrong: "#a1a1a1",
    accent: "#a3a3a3", accentTop: "#ededed",
    wa: "#fafafa", tg: "#737373",
    tooltipBg: "#171717", tooltipBorder: "#2a2a2a", tooltipInk: "#fafafa",
    glow: "rgba(255,255,255,0.45)",
  },
  light: {
    grid: "#e5e5e5", axis: "#737373", axisStrong: "#525252",
    accent: "#525252", accentTop: "#171717",
    wa: "#171717", tg: "#a3a3a3",
    tooltipBg: "#ffffff", tooltipBorder: "#e5e5e5", tooltipInk: "#0a0a0a",
    glow: "rgba(0,0,0,0.15)",
  },
};

type Ctx = { theme: Theme; setTheme: (t: Theme) => void; toggle: () => void; chart: ChartTheme };
const ThemeContext = createContext<Ctx | null>(null);
const STORAGE_KEY = "aznet.theme";

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  });

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    localStorage.setItem(STORAGE_KEY, t);
  }, []);
  const toggle = useCallback(() => setTheme(theme === "dark" ? "light" : "dark"), [theme, setTheme]);

  // Tailwind darkMode:"class" reads this class on <html>.
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggle, chart: CHART[theme] }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): Ctx {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
